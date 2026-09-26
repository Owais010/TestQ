"""Docker lifecycle and bounded execution; no repository commands run on host."""
import io
import math
import shlex
import tarfile
import time
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.types import LogConfig, Ulimit

from app.config import settings, APP_ROOT
from app.schemas.common import ExecutionResult, SandboxConfig
from app.worker.control import RunControl


class SandboxError(Exception):
    pass


class SandboxCreationError(SandboxError):
    pass


class SandboxExecutionError(SandboxError):
    pass


class SandboxTimeoutError(SandboxError):
    pass


class SandboxManager:
    """One manager owns a run's containers from before create until removal.

    Blocking SDK requests have a transport timeout. Cancellation/deadlines kill
    the entire container (including descendants), then retain files until export.
    PID 1 also limits container lifetime if the backend disappears.
    """
    LOG_LIMIT = 10 * 1024 * 1024

    def __init__(self, control: RunControl | None = None, run_id: str | None = None):
        self.control = control
        self.run_id = run_id or uuid.uuid4().hex
        self.owned: set[str] = set()
        self.executions: dict[str, list[tuple[str, str, str]]] = {}
        self.client = docker.from_env(timeout=settings.docker_api_timeout)
        self.client.ping()

    def check(self):
        if self.control:
            self.control.check()

    def create(self, config: SandboxConfig, repo_path=None) -> dict:
        self.check()
        name = f"testq-{self.run_id}-{uuid.uuid4().hex[:8]}"
        # Track name BEFORE the request: also covers a lost create response.
        self.owned.add(name)
        lifetime = min(config.timeout, self.control.remaining if self.control else config.timeout)
        browser_options = {}
        security = ["no-new-privileges"]
        if config.browser_enabled:
            profile = json.loads((APP_ROOT / "sandbox/seccomp-browser.json").read_text(encoding="utf-8-sig"))
            # glibc falls back to clone when clone3 reports ENOSYS; never allow it unfiltered.
            profile["syscalls"].append({"names": ["clone3"], "action": "SCMP_ACT_ERRNO", "errnoRet": 38})
            # Chromium chroots inside its own user namespace. The upstream profile
            # gates this syscall on container CAP_SYS_CHROOT, which we drop. Allow
            # the syscall, not the capability; kernel namespace permissions remain.
            profile["syscalls"].append({"names": ["chroot"], "action": "SCMP_ACT_ALLOW"})
            security.append("seccomp=" + json.dumps(profile))
            browser_options["shm_size"] = "256m"  # private IPC, never --ipc=host
        try:
            container = self.client.containers.create(
                image=config.image, name=name,
                command=["sh", "-c", f"sleep {max(1, math.ceil(lifetime))}"],
                working_dir=config.working_dir,
                environment=config.environment,
                user="10001:10001", init=True,
                network_mode="bridge",
                ports={p: ("127.0.0.1", h or None) for p, h in config.port_mappings.items()},
                labels={"testq.managed": "true", "testq.run_id": self.run_id},
                security_opt=security, cap_drop=["ALL"], **browser_options,
                nano_cpus=int(config.cpu_limit * 1e9),
                mem_limit=config.memory_limit, memswap_limit=config.memory_limit,
                pids_limit=256, privileged=False,
                ulimits=[Ulimit(name="nofile", soft=4096, hard=4096)],
                log_config=LogConfig(type="json-file", config={"max-size": "10m", "max-file": "2"}),
            )
            self.check()
            container.start()
            if repo_path:
                self._copy_repo(container, repo_path, config.working_dir)
            self.check()
            container.reload()
            ports = {int(p.split('/')[0]): int(v[0]['HostPort'])
                     for p, v in (container.ports or {}).items() if v}
            return {"container_id": container.id, "short_id": container.short_id,
                    "assigned_ports": ports, "status": "running"}
        except BaseException:
            # Keep ownership if removal fails so the outer finally retries it.
            self.destroy(name)
            raise

    def _copy_repo(self, container, repo_path, working_dir):
        root = Path(repo_path).resolve()
        if not root.is_dir():
            raise SandboxCreationError(f"Repository directory missing: {root}")
        total_size = 0
        def safe_member(info):
            nonlocal total_size
            self.check()
            if any(p in {".git", "node_modules", ".venv", "venv", "__pycache__"}
                   for p in Path(info.name).parts):
                return None
            if info.issym() or info.islnk():
                target = (root / info.name).resolve()
                if not target.is_relative_to(root):
                    raise SandboxCreationError(f"Repository link escapes workspace: {info.name}")
            if not (info.isfile() or info.isdir() or info.issym()):
                raise SandboxCreationError(f"Unsupported repository file: {info.name}")
            total_size += info.size
            if total_size > 256 * 1024 * 1024:
                raise SandboxCreationError("Repository exceeds 256 MiB sandbox copy limit")
            info.uid = info.gid = 10001
            info.uname = info.gname = "testq"
            info.mode &= 0o777  # remove setuid/setgid/sticky bits
            return info
        with io.BytesIO() as stream:
            with tarfile.open(fileobj=stream, mode="w") as archive:
                for item in root.iterdir():
                    archive.add(item, arcname=item.name, filter=safe_member)
            self.check()
            container.put_archive(working_dir, stream.getvalue())

    def restrict_network(self, container_id):
        """Runtime has loopback only; no bridge, DNS, host or internet route."""
        self.check()
        container = self.client.containers.get(container_id)
        container.reload()
        for name in list(container.attrs["NetworkSettings"]["Networks"]):
            self.client.networks.get(name).disconnect(container, force=True)
        container.reload()
        if container.attrs["NetworkSettings"]["Networks"]:
            raise SandboxError("Runtime network isolation failed")
        self.check()

    def _launch(self, container_id, command, working_dir, source, environment=None, user="10001:10001"):
        self.check()
        token = uuid.uuid4().hex
        stdout = f"/tmp/testq-{token}.stdout"
        stderr = f"/tmp/testq-{token}.stderr"
        self.executions.setdefault(container_id, []).append((source, stdout, stderr))
        # RLIMIT_FSIZE bounds each output file to 10 MiB (dash uses 512-byte blocks).
        wrapped = f"ulimit -f 20480; exec sh -c {shlex.quote(command)} >{stdout} 2>{stderr}"
        result = self.client.api.exec_create(
            container_id, cmd=["sh", "-c", wrapped], workdir=working_dir,
            user=user, environment=environment or {},
        )
        self.client.api.exec_start(result["Id"], detach=True)
        return result["Id"], stdout, stderr

    def execute(self, container_id, command, timeout=None, working_dir=None,
                source="command", environment=None, user="10001:10001"):
        timeout = timeout if timeout is not None else settings.docker_timeout
        started = datetime.now(timezone.utc)
        begin = time.monotonic()
        if user == "10001:10001":
            exec_id, stdout, stderr = self._launch(container_id, command, working_dir, source, environment)
        else:
            exec_id, stdout, stderr = self._launch(container_id, command, working_dir, source, environment, user=user)
        timed_out = False
        try:
            while True:
                self.check()
                if time.monotonic() - begin >= timeout:
                    self.kill(container_id)
                    timed_out = True
                    code = 124
                    break
                state = self.client.api.exec_inspect(exec_id)
                if not state["Running"]:
                    code = state["ExitCode"]
                    break
                time.sleep(0.1)
        except BaseException:
            self.kill(container_id)
            raise
        return ExecutionResult(
            command=command, exit_code=code if code is not None else -1,
            stdout=self.read_file(container_id, stdout),
            stderr=self.read_file(container_id, stderr),
            started_at=started, finished_at=datetime.now(timezone.utc),
            duration_seconds=time.monotonic() - begin, timed_out=timed_out,
        )

    def execute_detached(self, container_id, command, working_dir=None, environment=None):
        return self._launch(container_id, command, working_dir, "application", environment)[0]

    def read_file(self, container_id, path):
        """Read a bounded regular file, including from a stopped container.

        Never extract container-provided archive paths onto the host.
        """
        try:
            chunks, _ = self.client.containers.get(container_id).get_archive(path)
            with io.BytesIO() as buffer:
                for chunk in chunks:
                    buffer.write(chunk)
                    if buffer.tell() > self.LOG_LIMIT + 1024 * 1024:
                        raise SandboxError("Log archive exceeds retention limit")
                buffer.seek(0)
                with tarfile.open(fileobj=buffer) as archive:
                    member = archive.next()
                    if member is None or not member.isfile() or member.size > self.LOG_LIMIT:
                        raise SandboxError("Invalid log archive")
                    return archive.extractfile(member).read(self.LOG_LIMIT).decode("utf-8", errors="replace")
        except NotFound:
            return ""

    def collect_logs(self, container_id):
        output = []
        for source, stdout, stderr in self.executions.get(container_id, []):
            if source.startswith("_"):
                continue
            for stream, path in (("stdout", stdout), ("stderr", stderr)):
                value = self.read_file(container_id, path)
                if value:
                    output.append((source, stream, value))
        return output

    def read_artifact(self, container_id, session_id, filename, max_bytes):
        """Bounded binary export, also valid after timeout kills the container."""
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",session_id) or not re.fullmatch(r"[a-zA-Z0-9_-]+\.(json|png|zip)",filename):
            raise SandboxError("Invalid artifact path")
        chunks,_ = self.client.containers.get(container_id).get_archive(f"/discovery/{session_id}/{filename}")
        with io.BytesIO() as buffer:
            for chunk in chunks:
                buffer.write(chunk)
                if buffer.tell() > max_bytes + 1024*1024:
                    raise SandboxError("Artifact archive exceeds budget")
            buffer.seek(0)
            with tarfile.open(fileobj=buffer) as archive:
                member = archive.next()
                if not member or not member.isfile() or member.size > max_bytes:
                    raise SandboxError("Artifact is not a bounded regular file")
                return archive.extractfile(member).read(max_bytes+1)

    def browser_available(self, tag):
        return self.client.images.get(tag).labels.get("testq.browser") == "1.63.0"

    def stream_logs(self, container_id, tail=100):
        return "\n".join("\n".join(value for _, _, value in self.collect_logs(container_id)).splitlines()[-tail:])

    def kill(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            if container.status == "running":
                container.kill()
        except NotFound:
            pass

    def stop(self, container_id, timeout=10):
        self.kill(container_id)

    def destroy(self, container_id):
        try:
            self.client.containers.get(container_id).remove(force=True, v=True)
        except NotFound:
            pass
        self.owned.discard(container_id)

    def cleanup(self):
        errors = []
        for name in list(self.owned):
            for attempt in range(3):
                try:
                    self.destroy(name)
                    break
                except Exception as error:
                    if attempt == 2:
                        errors.append(f"{name}: {error}")
                    else:
                        time.sleep(0.2)
        if errors:
            raise SandboxError("Cleanup failed; retry required: " + "; ".join(errors))

    def adopt_run(self, run_id):
        """Recover only labelled containers for this run after worker loss."""
        for container in self.client.containers.list(all=True, filters={
            "label": ["testq.managed=true", f"testq.run_id={run_id}"]
        }):
            self.owned.add(container.id)

    def get_port_mapping(self, container_id, container_port):
        container = self.client.containers.get(container_id)
        container.reload()
        value = (container.ports or {}).get(f"{container_port}/tcp")
        return int(value[0]["HostPort"]) if value else None

    def is_running(self, container_id):
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            return container.status == "running"
        except NotFound:
            return False

    def image_exists(self, tag):
        try:
            image = self.client.images.get(tag)
            return image.labels.get("testq.hardening") == "1"
        except NotFound:
            return False
