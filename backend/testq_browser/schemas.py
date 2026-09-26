"""Typed wire contract for sandbox discovery, persistence and evidence export."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


def now():
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoveryLimits(Model):
    max_pages: int = Field(12, ge=1, le=50)
    max_depth: int = Field(3, ge=0, le=8)
    navigation_timeout: float = Field(8, gt=0, le=60)
    action_timeout: float = Field(3, gt=0, le=15)
    discovery_timeout: float = Field(60, gt=0, le=300)
    max_elements: int = Field(200, ge=1, le=500)
    max_observations: int = Field(1000, ge=1, le=5000)
    max_requests: int = Field(1000, ge=1, le=5000)
    max_artifact_bytes: int = Field(8 * 1024**2, ge=1024, le=10 * 1024**2)
    max_evidence_bytes: int = Field(64 * 1024**2, ge=4096, le=128 * 1024**2)
    trace_enabled: bool = True


class SelectorCandidate(Model):
    strategy: Literal["test_id", "role", "id", "name", "attribute", "css"]
    value: str = Field(max_length=1000)
    role: str | None = None
    exact: bool = True


class Element(Model):
    tag: str
    role: str = ""
    accessible_name: str = ""
    text: str = ""
    element_id: str = ""
    input_type: str = ""
    name: str = ""
    placeholder: str = ""
    label: str = ""
    required: bool = False
    disabled: bool = False
    checked: bool | None = None
    multiple: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    selectors: list[SelectorCandidate] = Field(default_factory=list, max_length=10)


class Form(Model):
    identifier: str
    action: str
    method: str
    controls: list[Element] = Field(default_factory=list, max_length=500)
    buttons: list[Element] = Field(default_factory=list, max_length=500)


class Link(Model):
    href: str
    text: str
    source_page: str
    internal: bool


class Observation(Model):
    run_id: str
    session_id: str
    page_url: str
    timestamp: datetime = Field(default_factory=now)
    kind: Literal["console_log", "console_warn", "console_error", "console_info", "console_debug",
                  "browser_error", "request_failed", "external_blocked", "navigation_error",
                  "browser_crash", "discovery_timeout", "limit_reached", "evidence_error", "application_error"]
    message: str = Field(max_length=4000)


class NetworkRequest(Model):
    page_url: str
    timestamp: datetime = Field(default_factory=now)
    method: str
    url: str
    path: str
    resource_type: str
    status: int | None = Field(None, ge=100, le=599)
    duration_ms: float | None = None
    failure: str | None = None
    internal: bool


class APIEndpoint(Model):
    method: str
    path: str
    statuses: list[int] = Field(default_factory=list)


class Artifact(Model):
    kind: Literal["screenshot", "trace", "console", "network", "browser_error", "application_log", "application_map"]
    filename: str
    page_url: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str
    @field_validator("filename")
    @classmethod
    def safe_name(cls, value):
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.(png|zip|json)", value):
            raise ValueError("Artifact filename must be a single safe basename")
        return value


class PageRecord(Model):
    url: str
    final_url: str = ""
    depth: int = Field(ge=0)
    title: str = ""
    timestamp: datetime = Field(default_factory=now)
    navigation: Literal["pending", "ok", "http_error", "timeout", "failed"] = "pending"
    status: int | None = Field(None, ge=100, le=599)
    screenshot: str | None = None
    links: list[Link] = Field(default_factory=list, max_length=500)
    buttons: list[Element] = Field(default_factory=list, max_length=500)
    inputs: list[Element] = Field(default_factory=list, max_length=500)
    forms: list[Form] = Field(default_factory=list, max_length=500)


class ApplicationMap(Model):
    schema_version: int = 1
    run_id: str
    session_id: str
    base_url: str
    status: Literal["running", "completed", "failed", "timed_out", "cancelled"] = "running"
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    pages: list[PageRecord] = Field(default_factory=list, max_length=50)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list, max_length=5000)
    requests: list[NetworkRequest] = Field(default_factory=list, max_length=5000)
    observations: list[Observation] = Field(default_factory=list, max_length=5000)
    artifacts: list[Artifact] = Field(default_factory=list, max_length=110)
    limits: DiscoveryLimits = Field(default_factory=DiscoveryLimits)
    truncated: bool = False
    error: str | None = None


class DiscoveryRequest(Model):
    run_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    session_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    base_url: str
    limits: DiscoveryLimits = Field(default_factory=DiscoveryLimits)
    @field_validator("base_url")
    @classmethod
    def local_application(cls, value):
        from urllib.parse import urlsplit
        url = urlsplit(value)
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.username or url.password:
            raise ValueError("Discovery target must be an explicit loopback HTTP port")
        if url.path not in ("", "/") or url.query or url.fragment:
            raise ValueError("Discovery starts at the application root")
        return f"http://127.0.0.1:{url.port}"
