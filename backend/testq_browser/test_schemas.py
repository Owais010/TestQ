"""Phase 3 deterministic test schemas and models — strictly bounded, safe inside sandbox."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

class SelectorSpec(StrictModel):
    """Reference to a page element using the Phase 2 selector candidate strategies."""
    strategy: Literal["test_id", "role", "id", "name", "attribute", "css"]
    value: str = Field(min_length=1, max_length=1000)
    role: str | None = None  # required when strategy == "role"
    exact: bool = True

    @model_validator(mode="after")
    def role_strategy_requires_role(self):
        if self.strategy == "role" and not self.role:
            raise ValueError("strategy='role' requires the 'role' field")
        return self


# ---------------------------------------------------------------------------
# UI test steps
# ---------------------------------------------------------------------------

class UITestStep(StrictModel):
    """A single deterministic Playwright action."""
    action: Literal["goto", "click", "fill", "select", "check", "uncheck", "wait"]
    target: str | None = Field(None, max_length=2000)
    value: str | None = Field(None, max_length=10000)
    selector: SelectorSpec | None = None
    candidates: list[SelectorSpec] | None = Field(None, max_length=10)
    timeout_ms: int | None = Field(None, ge=100, le=30000)

    @model_validator(mode="before")
    @classmethod
    def normalize_step_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize action synonyms
            act = str(data.get("action", "")).lower()
            if act in ("navigate", "open"):
                data["action"] = "goto"
            elif act in ("type", "input"):
                data["action"] = "fill"
            elif act in ("press", "tap"):
                data["action"] = "click"
            elif act in ("check_url", "verify_url"):
                data["action"] = "goto"
            elif act in ("element_exists", "is_visible", "assert", "verify"):
                data["action"] = "wait"
            elif act:
                data["action"] = act

            if "selector" in data and isinstance(data["selector"], str):
                if not data.get("target"):
                    data["target"] = data.pop("selector")
                else:
                    data.pop("selector")
            allowed = {"action", "target", "value", "selector", "candidates", "timeout_ms"}
            return {k: v for k, v in data.items() if k in allowed}
        return data

    @model_validator(mode="after")
    def validate_step(self):
        if self.action == "goto":
            if not self.target:
                raise ValueError("goto requires a target path")
            if self.target.startswith(("http://", "https://")):
                raise ValueError("goto target must be a relative path, not an absolute URL")
            if not self.target.startswith("/"):
                raise ValueError("goto target must start with /")
        elif self.action in ("click", "check", "uncheck"):
            if not self.selector and not self.target and not self.candidates:
                raise ValueError(f"{self.action} requires a selector, candidates, or target")
        elif self.action == "fill":
            if not self.selector and not self.target and not self.candidates:
                raise ValueError("fill requires a selector, candidates, or target")
            if self.value is None:
                raise ValueError("fill requires a value")
        elif self.action == "select":
            if not self.selector and not self.target and not self.candidates:
                raise ValueError("select requires a selector, candidates, or target")
            if self.value is None:
                raise ValueError("select requires a value")
        elif self.action == "wait":
            if self.timeout_ms is None:
                self.timeout_ms = 1000
        return self


# ---------------------------------------------------------------------------
# UI test assertions
# ---------------------------------------------------------------------------

class UIAssertion(StrictModel):
    """A deterministic assertion about page state."""
    assertion: Literal[
        "page_loaded", "url_matches", "text_visible",
        "element_visible", "element_hidden", "input_value", "http_status",
    ]
    expected: str | None = Field(None, max_length=10000)
    selector: SelectorSpec | None = None
    candidates: list[SelectorSpec] | None = Field(None, max_length=10)

    @model_validator(mode="before")
    @classmethod
    def normalize_assertion_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize assertion name synonyms
            ass = str(data.get("assertion", "")).lower()
            if ass in ("url_contains", "url_equals", "path_matches"):
                data["assertion"] = "url_matches"
            elif ass in ("element_exists", "is_visible", "should_be_visible"):
                data["assertion"] = "element_visible"
            elif ass in ("element_not_exists", "is_hidden", "should_be_hidden"):
                data["assertion"] = "element_hidden"
            elif ass in ("contains_text", "has_text", "text_contains"):
                data["assertion"] = "text_visible"
            elif ass:
                data["assertion"] = ass

            if not data.get("expected") and "value" in data:
                data["expected"] = str(data.pop("value"))
            if not data.get("expected") and "target" in data:
                data["expected"] = str(data.pop("target"))

            if "selector" in data and isinstance(data["selector"], str):
                if not data.get("expected"):
                    data["expected"] = data.pop("selector")
                else:
                    data.pop("selector")
            allowed = {"assertion", "expected", "selector", "candidates"}
            return {k: v for k, v in data.items() if k in allowed}
        return data

    @model_validator(mode="after")
    def validate_assertion(self):
        if self.assertion == "url_matches" and not self.expected:
            raise ValueError("url_matches requires an expected value")
        if self.assertion == "text_visible" and not self.expected:
            raise ValueError("text_visible requires an expected value")
        if self.assertion in ("element_visible", "element_hidden"):
            if not self.selector and not self.expected and not self.candidates:
                raise ValueError(f"{self.assertion} requires a selector, candidates, or expected value")
        if self.assertion == "input_value":
            if not self.selector and not self.candidates:
                raise ValueError("input_value requires a selector or candidates")
            if self.expected is None:
                raise ValueError("input_value requires an expected value")
        if self.assertion == "http_status" and not self.expected:
            raise ValueError("http_status requires an expected status code")
        return self


# ---------------------------------------------------------------------------
# UI test definition
# ---------------------------------------------------------------------------

class UITestDefinition(StrictModel):
    """Complete structured UI test case — no arbitrary code execution."""
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    type: Literal["ui"] = "ui"
    title: str = Field(min_length=1, max_length=500)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    steps: list[UITestStep] = Field(min_length=1, max_length=50)
    expected: list[UIAssertion] = Field(min_length=1, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def normalize_ui_test(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "title" not in data and "name" in data:
                data["title"] = data["name"]
            if not data.get("title"):
                data["title"] = "UI Test Case"
            if "type" not in data:
                data["type"] = "ui"
            raw_id = str(data.get("id", "AI-UI-001")).upper().replace(" ", "_")
            if not re.match(r"^[A-Z][A-Z0-9_-]{1,63}$", raw_id):
                raw_id = f"AI-UI-{abs(hash(str(data.get('title', 'test')))) % 1000:03d}"
            data["id"] = raw_id
            pri = str(data.get("priority", "medium")).lower()
            if pri not in ("critical", "high", "medium", "low"):
                pri = "medium"
            data["priority"] = pri
            allowed = {"id", "type", "title", "priority", "steps", "expected"}
            return {k: v for k, v in data.items() if k in allowed}
        return data

    @field_validator("steps")
    @classmethod
    def limit_steps(cls, v):
        if len(v) > 50:
            raise ValueError("Too many steps (max 50)")
        return v


# ---------------------------------------------------------------------------
# API test definitions
# ---------------------------------------------------------------------------

_SAFE_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_SAFE_HEADER_NAMES = frozenset({
    "accept", "content-type", "x-requested-with", "cache-control",
    "accept-language", "accept-encoding",
})


class APIRequestSpec(StrictModel):
    """Controlled API request targeting only the local application."""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str = Field(min_length=1, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: dict | list | str | None = None
    timeout_ms: int = Field(5000, ge=100, le=30000)

    @model_validator(mode="before")
    @classmethod
    def normalize_request_spec(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "method" in data:
                data["method"] = str(data["method"]).upper()
            if "path" in data and not str(data["path"]).startswith(("/", "http://", "https://", "//")):
                data["path"] = f"/{data['path']}"
            allowed = {"method", "path", "headers", "query", "body", "timeout_ms"}
            return {k: v for k, v in data.items() if k in allowed}
        return data

    @field_validator("path")
    @classmethod
    def relative_path_only(cls, v):
        if v.startswith(("http://", "https://")):
            raise ValueError("API path must be relative, not an absolute URL")
        if v.startswith("//"):
            raise ValueError("Protocol-relative URLs are prohibited")
        if not v.startswith("/"):
            raise ValueError("API path must start with /")
        return v

    @field_validator("headers")
    @classmethod
    def safe_headers_only(cls, v):
        for name in v:
            if name.lower() not in _SAFE_HEADER_NAMES:
                raise ValueError(f"Header '{name}' is not in the safe header allowlist")
        return v


class APIAssertion(StrictModel):
    """Deterministic assertion about an API response."""
    assertion: Literal[
        "status_code", "response_time", "json_field_present",
        "json_value", "content_type",
    ]
    expected: str | int | float | bool | None = None
    field: str | None = Field(None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def normalize_api_assertion(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ass = str(data.get("assertion", "")).lower()
            if ass in ("status", "http_status", "status_code_equals"):
                data["assertion"] = "status_code"
            elif ass in ("response_contains", "body_contains"):
                data["assertion"] = "status_code"
                data["expected"] = 200
            elif ass:
                data["assertion"] = ass
            if not data.get("expected") and "value" in data:
                data["expected"] = data.pop("value")
            if data.get("assertion") == "status_code" and isinstance(data.get("expected"), str):
                try:
                    data["expected"] = int(data["expected"])
                except ValueError:
                    pass
            allowed = {"assertion", "expected", "field"}
            return {k: v for k, v in data.items() if k in allowed}
        return data

    @model_validator(mode="after")
    def validate_assertion(self):
        if self.assertion == "status_code" and self.expected is None:
            raise ValueError("status_code requires an expected value")
        if self.assertion == "json_field_present" and not self.field:
            raise ValueError("json_field_present requires a field path")
        if self.assertion == "json_value":
            if not self.field:
                raise ValueError("json_value requires a field path")
            if self.expected is None:
                raise ValueError("json_value requires an expected value")
        if self.assertion == "content_type" and not self.expected:
            raise ValueError("content_type requires an expected value")
        return self


class APITestDefinition(StrictModel):
    """Complete structured API test case — only targets local application."""
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    type: Literal["api"] = "api"
    title: str = Field(min_length=1, max_length=500)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    request: APIRequestSpec
    expected: list[APIAssertion] = Field(min_length=1, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def normalize_api_test(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "title" not in data and "name" in data:
                data["title"] = data["name"]
            if not data.get("title"):
                data["title"] = "API Test Case"
            if "type" not in data:
                data["type"] = "api"
            raw_id = str(data.get("id", "AI-API-001")).upper().replace(" ", "_")
            if not re.match(r"^[A-Z][A-Z0-9_-]{1,63}$", raw_id):
                raw_id = f"AI-API-{abs(hash(str(data.get('title', 'test')))) % 1000:03d}"
            data["id"] = raw_id
            pri = str(data.get("priority", "medium")).lower()
            if pri not in ("critical", "high", "medium", "low"):
                pri = "medium"
            data["priority"] = pri

            # Normalize request if given as a string e.g. "POST /api/users"
            req = data.get("request")
            if isinstance(req, str):
                parts = req.strip().split()
                if len(parts) >= 2:
                    data["request"] = {"method": parts[0].upper(), "path": parts[1]}
                elif len(parts) == 1:
                    data["request"] = {"method": "GET", "path": parts[0] if parts[0].startswith("/") else f"/{parts[0]}"}
                else:
                    data["request"] = {"method": "GET", "path": "/"}

            allowed = {"id", "type", "title", "priority", "request", "expected"}
            return {k: v for k, v in data.items() if k in allowed}
        return data


# ---------------------------------------------------------------------------
# Union type used by the executor
# ---------------------------------------------------------------------------

TestDefinition = UITestDefinition | APITestDefinition


def validate_test_definition(data: dict) -> TestDefinition:
    """Parse and validate a test definition from a dict, rejecting unknown types."""
    test_type = data.get("type")
    if test_type == "ui":
        return UITestDefinition.model_validate(data)
    elif test_type == "api":
        return APITestDefinition.model_validate(data)
    else:
        raise ValueError(f"Unknown test type: {test_type!r}")


# ---------------------------------------------------------------------------
# Test result schema (returned by executor)
# ---------------------------------------------------------------------------

class TestResultStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    ALL = {PASS, FAIL, ERROR, TIMEOUT, CANCELLED}


class AssertionResult(StrictModel):
    assertion: str
    passed: bool
    expected: str | None = None
    actual: str | None = None
    error: str | None = None


class StepResult(StrictModel):
    action: str
    target: str | None = None
    status: Literal["ok", "error", "timeout"] = "ok"
    duration_ms: float = 0.0
    error: str | None = None


class TestExecutionResult(StrictModel):
    """Structured result produced by in-sandbox test runners."""
    __test__ = False
    test_id: str
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime
    duration_ms: float = 0.0
    steps: list[StepResult] = Field(default_factory=list)
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: str | None = None
    evidence_files: list[str] = Field(default_factory=list)
    http_status: int | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v not in TestResultStatus.ALL:
            raise ValueError(f"Invalid test result status: {v}")
        return v


# ---------------------------------------------------------------------------
# Test artifact model
# ---------------------------------------------------------------------------

_TEST_EVIDENCE_KINDS = frozenset({
    "test_screenshot", "test_trace", "test_console",
    "test_network", "test_error", "test_result",
})


class TestArtifact(StrictModel):
    """Phase 3 test evidence artifact — separate from discovery artifacts."""
    __test__ = False
    kind: Literal[
        "test_screenshot", "test_trace", "test_console",
        "test_network", "test_error", "test_result",
    ]
    filename: str
    page_url: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str

    @field_validator("filename")
    @classmethod
    def safe_name(cls, value):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.(png|zip|json)", value):
            raise ValueError("Test artifact filename must be a single safe basename")
        return value
