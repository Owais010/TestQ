"""Install/build with development dependencies; start with production settings."""
from app.config import settings
from app.schemas.common import ProjectConfig, ExecutionResult


class BuildError(Exception):
    def __init__(self, stage: str, result: ExecutionResult):
        self.stage, self.result = stage, result
        detail = "command timed out and container terminated" if result.timed_out else f"exit_code={result.exit_code}"
        super().__init__(f"{stage} failed: {detail}; {result.stderr[-2000:] or result.stdout[-2000:]}")


class BuildManager:
    def __init__(self, sandbox):
        self.sandbox = sandbox

    @staticmethod
    def workdir(config):
        return "/workspace" + ("/" + config.project_dir if config.project_dir != "." else "")

    def _execute(self, stage, container_id, config, command, timeout):
        result = self.sandbox.execute(
            container_id, command, timeout=timeout or settings.docker_timeout,
            working_dir=self.workdir(config), source=stage,
            environment={"NODE_ENV": "development", "NPM_CONFIG_PRODUCTION": "false"},
        )
        if result.timed_out or result.exit_code != 0:
            raise BuildError(stage, result)
        return result

    def install_dependencies(self, container_id, config, timeout=None):
        return self._execute("install", container_id, config, config.install_command, timeout)

    def build_project(self, container_id, config, timeout=None):
        if config.build_command:
            return self._execute("build", container_id, config, config.build_command, timeout)

    def start_application(self, container_id, config):
        return self.sandbox.execute_detached(
            container_id, config.start_command, working_dir=self.workdir(config),
            environment={"NODE_ENV": "production", "PORT": str(config.expected_port), "HOST": "0.0.0.0"},
        )
