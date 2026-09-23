"""
TestQ Pipeline — Phase 1 Execution Foundation.

Orchestrates the complete test run pipeline:
QUEUED → CLONING → ANALYZING → BUILDING → STARTING → READY

Each state transition is persisted to the database.
Failures are captured with full evidence and the pipeline stops honestly.

All synchronous operations (git, Docker SDK) are wrapped in
asyncio.to_thread() to avoid blocking the FastAPI event loop.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.test_run import TestRun, TestRunStatus
from app.models.log import Log
from app.schemas.common import ProjectConfig, SandboxConfig
from app.services.github_service import (
    GitHubService,
    GitHubServiceError,
)
from app.services.project_detector import (
    detect_project,
    UnsupportedProjectError,
    DetectionError,
)
from app.services.sandbox_manager import SandboxManager, SandboxError
from app.services.build_manager import BuildManager, BuildError
from app.services.health_checker import HealthChecker

logger = logging.getLogger("testq.pipeline")

# Sandbox Docker image tags
NODE_SANDBOX_IMAGE = "testq-sandbox-node:latest"
PYTHON_SANDBOX_IMAGE = "testq-sandbox-python:latest"


class Pipeline:
    """
    The Phase 1 execution pipeline.

    Runs the complete flow from cloning to health check.
    Updates the TestRun record at each state transition.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.github = GitHubService()
        self.sandbox = SandboxManager()
        self.build_manager = BuildManager(self.sandbox)
        self.health_checker = HealthChecker()

    async def run(self, test_run: TestRun) -> None:
        """Execute the full Phase 1 pipeline for a test run."""
        container_id = None
        repo_path = None

        try:
            test_run.started_at = datetime.now(timezone.utc)

            # === CLONING ===
            await self._update_status(test_run, TestRunStatus.CLONING)
            clone_result = await self._clone(test_run)
            repo_path = clone_result["repo_path"]
            test_run.commit_sha = clone_result.get("commit_sha")

            # === ANALYZING ===
            await self._update_status(test_run, TestRunStatus.ANALYZING)
            config = await self._analyze(test_run, repo_path)

            # === BUILDING ===
            await self._update_status(test_run, TestRunStatus.BUILDING)
            container_id = await self._build(test_run, config, repo_path)

            # === STARTING ===
            await self._update_status(test_run, TestRunStatus.STARTING)
            await self._start(test_run, config, container_id)

            # === READY ===
            await self._update_status(test_run, TestRunStatus.READY)
            await self._log(
                test_run, "system", "INFO",
                "Application is running and healthy. Pipeline Phase 1 complete."
            )

        except Exception as e:
            logger.error(f"Pipeline failed for run {test_run.id[:8]}: {e}")
            test_run.failure_reason = str(e) or repr(e)
            test_run.status = TestRunStatus.FAILED
            test_run.finished_at = datetime.now(timezone.utc)
            await self._log(test_run, "system", "ERROR", f"Pipeline failed: {e}")
            await self.db.commit()

        finally:
            if container_id:
                try:
                    await asyncio.to_thread(self.sandbox.destroy, container_id)
                except Exception as err:
                    logger.error(f"Sandbox cleanup error: {err}")
            if repo_path:
                try:
                    self.github.cleanup_workspace(repo_path)
                except Exception as err:
                    logger.error(f"Workspace cleanup error: {err}")

    async def _clone(self, test_run: TestRun) -> dict:
        """Clone the repository (runs in thread)."""
        await self._log(
            test_run, "clone", "INFO",
            f"Cloning {test_run.project.repository_url} (branch: {test_run.branch})"
        )

        try:
            result = await asyncio.to_thread(
                self.github.clone_repository,
                repository_url=test_run.project.repository_url,
                branch=test_run.branch,
            )
            await self._log(
                test_run, "clone", "INFO",
                f"Cloned successfully. Commit: {(result.get('commit_sha') or 'unknown')[:12]}"
            )
            return result

        except GitHubServiceError as e:
            test_run.failure_stage = "CLONING"
            await self._log(test_run, "clone", "ERROR", str(e))
            raise

    async def _analyze(self, test_run: TestRun, repo_path: str) -> ProjectConfig:
        """Detect the project type."""
        await self._log(test_run, "analyze", "INFO", "Analyzing project structure...")

        try:
            config = await asyncio.to_thread(detect_project, repo_path)

            test_run.detected_config = config.model_dump()

            project = test_run.project
            project.detected_framework = config.framework
            project.detected_language = config.language
            project.detected_package_manager = config.package_manager

            await self._log(
                test_run, "analyze", "INFO",
                f"Detected: {config.framework} ({config.language}), "
                f"PM: {config.package_manager}, Port: {config.expected_port}"
            )
            return config

        except UnsupportedProjectError as e:
            test_run.failure_stage = "ANALYZING"
            test_run.failure_reason = str(e)
            await self._log(test_run, "analyze", "ERROR", str(e))
            raise

        except DetectionError as e:
            test_run.failure_stage = "ANALYZING"
            test_run.failure_reason = str(e)
            await self._log(test_run, "analyze", "ERROR", str(e))
            raise

    async def _build(
        self, test_run: TestRun, config: ProjectConfig, repo_path: str
    ) -> str:
        """Create sandbox, install deps, build (all in threads)."""

        # Determine sandbox image
        image = PYTHON_SANDBOX_IMAGE if config.language == "python" else NODE_SANDBOX_IMAGE

        # Ensure image exists
        if not self.sandbox.image_exists(image):
            await self._log(test_run, "build", "INFO", f"Building sandbox image: {image}")
            sandbox_dir = Path(__file__).parent.parent.parent.parent / "sandbox"
            dockerfile = sandbox_dir / (
                "Dockerfile.python" if config.language == "python" else "Dockerfile.node"
            )
            if not dockerfile.exists():
                raise SandboxError(f"Sandbox Dockerfile not found: {dockerfile}")
            await asyncio.to_thread(self.sandbox.build_image, str(dockerfile), image)

        # Create sandbox with port mapping
        sandbox_config = SandboxConfig(
            image=image,
            cpu_limit=settings.docker_cpu_limit,
            memory_limit=settings.docker_memory_limit,
            timeout=settings.docker_timeout,
            port_mappings={config.expected_port: 0},  # 0 = auto-assign
        )

        await self._log(test_run, "build", "INFO", "Creating sandbox container...")
        sandbox_info = await asyncio.to_thread(
            self.sandbox.create, sandbox_config, repo_path
        )

        container_id = sandbox_info["container_id"]
        test_run.container_id = container_id

        if sandbox_info.get("assigned_ports"):
            host_port = sandbox_info["assigned_ports"].get(config.expected_port)
            if host_port:
                test_run.sandbox_port = host_port

        await self._log(
            test_run, "build", "INFO",
            f"Sandbox created: {sandbox_info['short_id']}"
        )

        # Install dependencies
        try:
            await self._log(
                test_run, "build", "INFO",
                f"Installing dependencies: {config.install_command}"
            )
            install_result = await asyncio.to_thread(
                self.build_manager.install_dependencies, container_id, config
            )
            await self._log(
                test_run, "build", "INFO",
                f"Dependencies installed ({install_result.duration_seconds:.1f}s)"
            )
        except BuildError as e:
            test_run.failure_stage = "BUILDING"
            test_run.failure_reason = (
                f"Dependency installation failed (exit_code={e.result.exit_code}): "
                f"{e.result.stderr[:500]}"
            )
            await self._log(
                test_run, "build", "ERROR",
                f"Install failed:\n{e.result.stderr[:1000]}"
            )
            raise

        # Build project
        try:
            await self._log(
                test_run, "build", "INFO",
                f"Building: {config.build_command or 'N/A'}"
            )
            build_result = await asyncio.to_thread(
                self.build_manager.build_project, container_id, config
            )
            if build_result:
                await self._log(
                    test_run, "build", "INFO",
                    f"Build completed ({build_result.duration_seconds:.1f}s)"
                )
            else:
                await self._log(test_run, "build", "INFO", "No build step — skipping")
        except BuildError as e:
            test_run.failure_stage = "BUILDING"
            test_run.failure_reason = (
                f"Build failed (exit_code={e.result.exit_code}): "
                f"{e.result.stderr[:500]}"
            )
            await self._log(
                test_run, "build", "ERROR",
                f"Build failed:\n{e.result.stderr[:1000]}"
            )
            raise

        return container_id

    async def _start(
        self, test_run: TestRun, config: ProjectConfig, container_id: str
    ) -> None:
        """Start the application and verify health."""
        await self._log(
            test_run, "startup", "INFO",
            f"Starting application: {config.start_command}"
        )

        await asyncio.to_thread(
            self.build_manager.start_application, container_id, config
        )

        # Give the app startup time
        await asyncio.sleep(3)

        # Get mapped host port
        host_port = test_run.sandbox_port
        if not host_port:
            host_port = self.sandbox.get_port_mapping(
                container_id, config.expected_port
            )
            if host_port:
                test_run.sandbox_port = host_port

        if not host_port:
            test_run.failure_stage = "STARTING"
            test_run.failure_reason = (
                f"Could not determine host port for container port {config.expected_port}"
            )
            raise SandboxError(test_run.failure_reason)

        # Health check
        url = f"http://localhost:{host_port}"
        await self._log(test_run, "startup", "INFO", f"Health checking: {url}")

        health = await self.health_checker.check(url)

        if not health.is_healthy:
            logs = self.sandbox.stream_logs(container_id, tail=50)
            test_run.failure_stage = "STARTING"
            test_run.failure_reason = (
                f"Health check failed after {health.attempts} attempts: {health.error}"
            )
            await self._log(
                test_run, "startup", "ERROR",
                f"Health check failed: {health.error}\nContainer logs:\n{logs[:2000]}"
            )
            raise SandboxError(test_run.failure_reason)

        await self._log(
            test_run, "startup", "INFO",
            f"Application healthy at {url} "
            f"(status={health.status_code}, "
            f"time={health.response_time_ms:.0f}ms, "
            f"attempts={health.attempts})"
        )

    async def _update_status(self, test_run: TestRun, new_status: str) -> None:
        """Update test run status with transition validation."""
        old_status = test_run.status

        if not test_run.can_transition_to(new_status):
            logger.warning(f"Invalid state transition: {old_status} -> {new_status}")

        test_run.status = new_status

        # Update progress dict
        progress = test_run.progress or {}
        stage_map = {
            TestRunStatus.CLONING: "cloning",
            TestRunStatus.ANALYZING: "analyzing",
            TestRunStatus.BUILDING: "building",
            TestRunStatus.STARTING: "starting",
            TestRunStatus.READY: "ready",
            TestRunStatus.TESTING: "testing",
            TestRunStatus.ANALYZING_FAILURES: "analyzing_failures",
            TestRunStatus.COMPLETED: "report",
        }

        for status, stage_key in stage_map.items():
            if status == new_status:
                progress[stage_key] = "in_progress"
                break
            else:
                progress[stage_key] = "completed"

        test_run.progress = progress
        await self.db.commit()

        logger.info(f"Run {test_run.id[:8]}: {old_status} -> {new_status}")

    async def _log(
        self, test_run: TestRun, source: str, level: str, message: str
    ) -> None:
        """Persist a log entry."""
        log = Log(run_id=test_run.id, source=source, level=level, message=message)
        self.db.add(log)
        await self.db.commit()

        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(f"[{test_run.id[:8]}][{source}] {message[:200]}")
