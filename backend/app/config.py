"""
TestQ Configuration.

All settings loaded from environment variables with sensible defaults.
V1 is 100% local/free — no paid APIs required.
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "sqlite+aiosqlite:///./testq.db"

    # AI Provider (V1: Ollama default)
    ai_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ai_model: str = "llama3.1"
    openai_api_key: str = ""

    # Docker Sandbox
    docker_timeout: int = 600  # seconds
    docker_cpu_limit: float = 2.0
    docker_memory_limit: str = "2g"

    # GitHub
    github_token: str = ""

    # Application
    host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_port: int = 3000
    evidence_dir: str = "./evidence"
    workspaces_dir: str = "./workspaces"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def evidence_path(self) -> Path:
        p = Path(self.evidence_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def workspaces_path(self) -> Path:
        p = Path(self.workspaces_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
