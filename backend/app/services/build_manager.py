"""
Build Manager.

Orchestrates the install → build → start pipeline inside a sandbox.
Captures full execution results (stdout, stderr, exit code, timing)
for every operation. Stops honestly on failure.

All sandbox calls are synchronous — callers wrap in asyncio.to_thread().
"""

import logging
from pathlib import Path

from app.schemas.common import ExecutionResult, ProjectConfig
from app.services.sandbox_manager import SandboxManager

logger = logging.getLogger("testq.build")


class BuildError(Exception):
    """Build pipeline failed."""

    def __init__(self, stage: str, result: ExecutionResult, message: str = ""):
        self.stage = stage
        self.result = result
        super().__init__(
            message or f"Build failed at stage '{stage}': exit_code={result.exit_code}"
        )


class BuildManager:
    """
    Manages the install → build → start pipeline.

    Each operation is executed in the sandbox and its result is fully captured.
    If any step fails, the pipeline STOPS and reports the failure honestly.
    All methods are synchronous (matching SandboxManager).
    """

    def __init__(self, sandbox: SandboxManager):
        self.sandbox = sandbox

    def install_dependencies(
        self,
        container_id: str,
        config: ProjectConfig,
        timeout: int = 300,
    ) -> ExecutionResult:
        """Install project dependencies. Raises BuildError if fails."""
        logger.info(f"Installing dependencies: {config.install_command}")

        result = self.sandbox.execute(
            container_id=container_id,
            command=config.install_command,
            timeout=timeout,
        )

        if result.exit_code != 0:
            logger.error(
                f"Dependency installation failed: exit_code={result.exit_code}\n"
                f"stderr: {result.stderr[:500]}"
            )
            raise BuildError("install", result)

        logger.info(
            f"Dependencies installed successfully ({result.duration_seconds:.1f}s)"
        )
        return result

    def build_project(
        self,
        container_id: str,
        config: ProjectConfig,
        timeout: int = 300,
    ) -> ExecutionResult | None:
        """Build the project. Returns None if no build command. Raises BuildError."""
        if not config.build_command:
            logger.info("No build command configured — skipping build step")
            return None

        logger.info(f"Building project: {config.build_command}")

        result = self.sandbox.execute(
            container_id=container_id,
            command=config.build_command,
            timeout=timeout,
        )

        if result.exit_code != 0:
            logger.error(
                f"Build failed: exit_code={result.exit_code}\n"
                f"stderr: {result.stderr[:500]}"
            )
            raise BuildError("build", result)

        logger.info(f"Build completed successfully ({result.duration_seconds:.1f}s)")
        return result

    def start_application(
        self,
        container_id: str,
        config: ProjectConfig,
    ) -> str:
        """
        Start the application server in the background.
        Returns the exec ID. Does NOT wait for the app to be ready.
        """
        env_prefix = ""
        if config.framework in ("nextjs", "vite-react", "nodejs"):
            env_prefix = "NODE_ENV=production PORT=$PORT "
        
        start_cmd = config.start_command
        if "$PORT" not in start_cmd:
            env_prefix += f"PORT={config.expected_port} "

        full_command = f"{env_prefix}{start_cmd}"
        logger.info(f"Starting application: {full_command}")

        exec_id = self.sandbox.execute_detached(
            container_id=container_id,
            command=full_command,
        )

        return exec_id
