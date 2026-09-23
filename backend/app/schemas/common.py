"""Common schemas used across services."""

from datetime import datetime
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Normalized project execution configuration produced by the detector."""

    language: str = Field(..., description="Primary language: typescript, javascript, python")
    framework: str = Field(..., description="Framework: nextjs, react, vite, nodejs, fastapi")
    package_manager: str = Field(
        ..., description="Package manager: npm, yarn, pnpm, pip"
    )
    install_command: str = Field(..., description="Command to install dependencies")
    build_command: str | None = Field(None, description="Command to build the project")
    start_command: str = Field(..., description="Command to start the application")
    expected_port: int = Field(3000, description="Expected port the app listens on")
    has_dockerfile: bool = Field(False, description="Whether the project has its own Dockerfile")
    detected_files: list[str] = Field(
        default_factory=list, description="Key files that informed detection"
    )


class ExecutionResult(BaseModel):
    """Result of executing a command in the sandbox."""

    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float = 0.0
    timed_out: bool = False


class SandboxConfig(BaseModel):
    """Configuration for creating a Docker sandbox."""

    image: str = Field(..., description="Docker image to use")
    cpu_limit: float = Field(2.0, description="CPU core limit")
    memory_limit: str = Field("2g", description="Memory limit")
    timeout: int = Field(600, description="Max execution time in seconds")
    working_dir: str = Field("/workspace", description="Working directory inside container")
    environment: dict[str, str] = Field(default_factory=dict)
    port_mappings: dict[int, int] = Field(
        default_factory=dict, description="container_port -> host_port"
    )


class HealthCheckResult(BaseModel):
    """Result of a health check against the running application."""

    is_healthy: bool
    url: str
    status_code: int | None = None
    response_time_ms: float | None = None
    error: str | None = None
    attempts: int = 0
