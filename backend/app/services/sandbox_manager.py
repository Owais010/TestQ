"""
Docker Sandbox Manager.

Creates and manages disposable Docker containers for safe execution
of untrusted repository code. This is the security boundary.

ALL methods are synchronous (Docker SDK is synchronous).
Callers should use asyncio.to_thread() when calling from async code.

CRITICAL SECURITY RULES:
- Never use --privileged
- Never expose Docker socket
- Never mount host filesystem (except controlled workspace copy)
- Always enforce CPU, memory, and time limits
- Always cleanup containers after use
"""

import io
import logging
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

import docker
from docker.errors import DockerException, NotFound, APIError
from docker.types import LogConfig

from app.config import settings
from app.schemas.common import ExecutionResult, SandboxConfig

logger = logging.getLogger("testq.sandbox")


class SandboxError(Exception):
    """Base sandbox error."""
    pass


class SandboxCreationError(SandboxError):
    """Failed to create sandbox container."""
    pass


class SandboxExecutionError(SandboxError):
    """Failed to execute command in sandbox."""
    pass


class SandboxTimeoutError(SandboxError):
    """Command timed out in sandbox."""
    pass


class SandboxManager:
    """
    Manages disposable Docker containers for safe code execution.

    Each test run gets its own container that is destroyed after use.
    All methods are synchronous — wrap with asyncio.to_thread() in async code.
    """

    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as e:
            raise SandboxError(
                f"Cannot connect to Docker. Is Docker Desktop running? Error: {e}"
            )

    def create(
        self,
        config: SandboxConfig,
        repo_path: str | Path | None = None,
    ) -> dict:
        """
        Create a new sandbox container.

        Returns dict with container_id, short_id, assigned_ports, status.
        """
        logger.info(
            f"Creating sandbox: image={config.image}, "
            f"cpu={config.cpu_limit}, mem={config.memory_limit}"
        )

        try:
            mem_bytes = self._parse_memory(config.memory_limit)

            # Build port mappings: {container_port: host_port_or_None}
            ports_dict = {}
            for container_port, host_port in config.port_mappings.items():
                ports_dict[container_port] = None if host_port == 0 else host_port

            container = self.client.containers.run(
                image=config.image,
                command="sleep infinity",
                working_dir=config.working_dir,
                environment=config.environment,
                ports=ports_dict,
                detach=True,
                security_opt=["no-new-privileges"],
                nano_cpus=int(config.cpu_limit * 1e9),
                mem_limit=mem_bytes,
                memswap_limit=mem_bytes,
                pids_limit=256,
                privileged=False,
                log_config=LogConfig(
                    type=LogConfig.types.JSON, config={"max-size": "10m"}
                ),
            )

            # Copy repository into container if provided
            if repo_path:
                self._copy_repo(container, repo_path, config.working_dir)

            container.reload()

            # Extract assigned host ports
            assigned_ports = {}
            if container.ports:
                for port_key, host_info in container.ports.items():
                    if host_info:
                        cport = int(port_key.split("/")[0])
                        assigned_ports[cport] = int(host_info[0]["HostPort"])

            logger.info(
                f"Sandbox created: {container.short_id}, ports: {assigned_ports}"
            )

            return {
                "container_id": container.id,
                "short_id": container.short_id,
                "assigned_ports": assigned_ports,
                "status": "running",
            }

        except DockerException as e:
            raise SandboxCreationError(
                f"Failed to create sandbox: {type(e).__name__}: {e}"
            )
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxCreationError(
                f"Unexpected sandbox error: {type(e).__name__}: {e}"
            )

    def _copy_repo(
        self, container, repo_path: str | Path, working_dir: str
    ) -> None:
        """Copy repository files into the container (excluding .git)."""
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise SandboxError(f"Repository path does not exist: {repo_path}")

        logger.info(f"Copying repository to container: {repo_path}")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            for item in repo_path.iterdir():
                if item.name == ".git":
                    continue
                tar.add(str(item), arcname=item.name)

        tar_stream.seek(0)
        container.put_archive(working_dir, tar_stream.getvalue())

    def execute(
        self,
        container_id: str,
        command: str,
        timeout: int | None = None,
        working_dir: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a command inside the sandbox container.

        Returns ExecutionResult with stdout, stderr, exit code, timing.
        """
        timeout = timeout or settings.docker_timeout

        logger.info(f"Executing in sandbox {container_id[:12]}: {command}")
        started_at = datetime.now(timezone.utc)

        try:
            container = self.client.containers.get(container_id)
        except NotFound:
            raise SandboxError(f"Container not found: {container_id[:12]}")

        try:
            exec_result = container.exec_run(
                cmd=["sh", "-c", command],
                workdir=working_dir,
                demux=True,
                stream=False,
            )

            finished_at = datetime.now(timezone.utc)
            duration = (finished_at - started_at).total_seconds()

            stdout = (
                exec_result.output[0].decode("utf-8", errors="replace")
                if exec_result.output[0]
                else ""
            )
            stderr = (
                exec_result.output[1].decode("utf-8", errors="replace")
                if exec_result.output[1]
                else ""
            )

            return ExecutionResult(
                command=command,
                exit_code=exec_result.exit_code,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=round(duration, 2),
                timed_out=duration >= timeout,
            )

        except APIError as e:
            finished_at = datetime.now(timezone.utc)
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Docker API error: {e}",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                timed_out=False,
            )

    def execute_detached(
        self,
        container_id: str,
        command: str,
        working_dir: str | None = None,
    ) -> str:
        """Start a long-running command in the background. Returns exec ID."""
        try:
            container = self.client.containers.get(container_id)
        except NotFound:
            raise SandboxError(f"Container not found: {container_id[:12]}")

        exec_id = container.client.api.exec_create(
            container.id,
            cmd=["sh", "-c", command],
            workdir=working_dir,
        )
        container.client.api.exec_start(exec_id["Id"], detach=True)

        logger.info(f"Started detached process in {container_id[:12]}: {command}")
        return exec_id["Id"]

    def get_port_mapping(
        self, container_id: str, container_port: int
    ) -> int | None:
        """Get the host port mapped to a container port."""
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            port_key = f"{container_port}/tcp"
            if container.ports and port_key in container.ports:
                host_info = container.ports[port_key]
                if host_info:
                    return int(host_info[0]["HostPort"])
            return None
        except (NotFound, KeyError, IndexError, TypeError):
            return None

    def stream_logs(self, container_id: str, tail: int = 100) -> str:
        """Get recent logs from the container."""
        try:
            container = self.client.containers.get(container_id)
            return container.logs(tail=tail, timestamps=True).decode(
                "utf-8", errors="replace"
            )
        except NotFound:
            return ""

    def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop the sandbox container."""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
            logger.info(f"Stopped sandbox: {container_id[:12]}")
        except NotFound:
            logger.warning(f"Container already removed: {container_id[:12]}")
        except APIError as e:
            logger.error(f"Error stopping container: {e}")

    def destroy(self, container_id: str) -> None:
        """Destroy the sandbox container. ALWAYS call after a test run."""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True, v=True)
            logger.info(f"Destroyed sandbox: {container_id[:12]}")
        except NotFound:
            logger.debug(f"Container already removed: {container_id[:12]}")
        except APIError as e:
            logger.error(f"Error destroying container: {e}")

    def is_running(self, container_id: str) -> bool:
        """Check if a container is still running."""
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            return container.status == "running"
        except NotFound:
            return False

    def _parse_memory(self, mem_str: str) -> int:
        """Parse memory limit string (e.g., '2g') to bytes."""
        mem_str = mem_str.lower().strip()
        multipliers = {"k": 1024, "m": 1024**2, "g": 1024**3}
        if mem_str[-1] in multipliers:
            return int(float(mem_str[:-1]) * multipliers[mem_str[-1]])
        return int(mem_str)

    def build_image(self, dockerfile_path: str, tag: str) -> str:
        """Build a Docker image from a Dockerfile."""
        path = Path(dockerfile_path)
        if not path.exists():
            raise SandboxError(f"Dockerfile not found: {dockerfile_path}")

        logger.info(f"Building image {tag} from {path.parent}")

        try:
            image, build_logs = self.client.images.build(
                path=str(path.parent),
                dockerfile=path.name,
                tag=tag,
                rm=True,
            )
            for log_entry in build_logs:
                if "stream" in log_entry:
                    logger.debug(log_entry["stream"].strip())
            return image.id
        except DockerException as e:
            raise SandboxError(f"Failed to build image: {e}")

    def image_exists(self, tag: str) -> bool:
        """Check if a Docker image exists locally."""
        try:
            self.client.images.get(tag)
            return True
        except (NotFound, DockerException):
            return False
