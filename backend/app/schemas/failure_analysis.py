"""
Schemas for AI Failure Analysis (Hackathon Hardening / Phase 4.5).
"""

from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class FailureSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureCategory(str, Enum):
    NAVIGATION = "navigation"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    INPUT = "input"
    UI = "UI"
    API = "API"
    WORKFLOW = "workflow"
    ERROR_HANDLING = "error_handling"
    UNKNOWN = "unknown"


class FailureAnalysis(BaseModel):
    """Structured AI failure analysis output."""
    __test__ = False

    title: str = Field(..., description="Short clear title describing the failure or defect")
    severity: FailureSeverity = Field(
        default=FailureSeverity.MEDIUM,
        description="Assessed severity level: low, medium, high, critical"
    )
    category: FailureCategory = Field(
        default=FailureCategory.UNKNOWN,
        description="Failure category: navigation, authentication, validation, input, UI, API, workflow, error_handling, unknown"
    )
    summary: str = Field(..., description="Concise summary of what failed and why it matters")
    likely_root_cause: str = Field(
        ...,
        description="Plausible technical root cause based on evidence, without pretending absolute certainty"
    )
    reproduction_steps: list[str] = Field(
        default_factory=list,
        description="Concrete, ordered reproduction steps to trigger the defect"
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="IDs or filenames of relevant screenshots, logs, or response artifacts"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0"
    )


class FailureItemResponse(BaseModel):
    """API response model for an analyzed failure finding."""
    __test__ = False

    id: str
    run_id: str
    test_result_id: str
    test_case_id: str
    test_title: str
    test_type: str  # "ui" or "api"
    test_source: str  # "baseline" or "ai"
    status: str  # FAIL, ERROR, TIMEOUT
    error: str | None = None
    title: str
    severity: str
    category: str
    summary: str
    likely_root_cause: str
    reproduction_steps: list[str]
    evidence_references: list[str]
    confidence: float
    created_at: datetime | None = None
