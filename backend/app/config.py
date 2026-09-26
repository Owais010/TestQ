"""Settings resolved against the repository root, never the process cwd."""
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

APP_ROOT = Path(__file__).resolve().parents[2]


def absolute_path(value: str) -> str:
    path = Path(value).expanduser()
    return str((path if path.is_absolute() else APP_ROOT / path).resolve())


class Settings(BaseSettings):
    APP_ROOT: Path = APP_ROOT
    database_url: str = "sqlite+aiosqlite:///./testq.db"
    ai_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ai_model: str = "qwen3:8b"
    ai_enabled: bool = True
    ai_max_generated_tests: int = Field(5, ge=1, le=100)
    ai_max_strategy_items: int = Field(5, ge=1, le=50)
    ai_max_retries: int = Field(2, ge=0, le=5)
    ai_request_timeout: float = Field(150.0, gt=0, le=300)
    ai_preflight_timeout: float = Field(15.0, gt=0, le=60)
    ai_planner_timeout: float = Field(90.0, gt=0, le=300)
    ai_generator_timeout: float = Field(150.0, gt=0, le=300)
    ai_analyzer_timeout: float = Field(60.0, gt=0, le=300)
    ai_max_output_bytes: int = Field(262144, ge=1024, le=1048576)
    openai_api_key: str = ""
    docker_timeout: float = Field(600, gt=0)
    run_timeout: float = Field(900, gt=0)
    docker_api_timeout: float = Field(15, gt=0)
    docker_cpu_limit: float = Field(2.0, gt=0)
    docker_memory_limit: str = "2g"
    github_token: str = ""
    host: str = "127.0.0.1"
    backend_port: int = Field(8000, ge=1, le=65535)
    frontend_port: int = Field(3000, ge=1, le=65535)
    evidence_dir: str = "./evidence"
    workspaces_dir: str = "./workspaces"
    log_level: str = "INFO"
    max_pages: int = Field(12, ge=1, le=50)
    max_depth: int = Field(3, ge=0, le=8)
    navigation_timeout: float = Field(8, gt=0, le=60)
    action_timeout: float = Field(3, gt=0, le=15)
    discovery_timeout: float = Field(60, gt=0, le=300)
    discovery_trace_enabled: bool = True

    # Phase 3: Deterministic testing limits
    max_tests_per_run: int = Field(50, ge=1, le=200)
    max_steps_per_test: int = Field(50, ge=1, le=100)
    test_timeout: float = Field(120, gt=0, le=600)
    test_action_timeout: float = Field(10, gt=0, le=60)

    def discovery_limits(self):
        from testq_browser.schemas import DiscoveryLimits
        return DiscoveryLimits(max_pages=self.max_pages,max_depth=self.max_depth,
            navigation_timeout=self.navigation_timeout,action_timeout=self.action_timeout,
            discovery_timeout=self.discovery_timeout,trace_enabled=self.discovery_trace_enabled)
    model_config = SettingsConfigDict(
        env_file=APP_ROOT / ".env", env_file_encoding="utf-8",
        validate_default=True, extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database(cls, value):
        url = make_url(value)
        if url.drivername in {"sqlite", "sqlite+aiosqlite"}:
            database = url.database
            if database and database != ":memory:":
                database = absolute_path(database)
            url = url.set(drivername="sqlite+aiosqlite", database=database)
        return url.render_as_string(hide_password=False)

    @field_validator("evidence_dir", "workspaces_dir")
    @classmethod
    def normalize_path(cls, value):
        return absolute_path(value)

    @property
    def evidence_path(self):
        path = Path(self.evidence_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def workspaces_path(self):
        path = Path(self.workspaces_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
