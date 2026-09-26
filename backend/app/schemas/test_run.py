"""TestRun API schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class TestRunCreate(BaseModel):
    """Request to create and start a test run."""
    __test__ = False

    repository_url: str = Field(
        ...,
        description="GitHub repository URL",
        examples=["https://github.com/user/project"],
    )
    branch: str | None = Field(None, description="Branch to test; omitted uses remote default")
    discover: bool = Field(True, description="Run deterministic browser discovery after health checking")
    testing_enabled: bool = Field(False, description="Run deterministic testing suite after discovery")


class TestRunProgress(BaseModel):
    """Real-time progress of a test run's pipeline stages."""
    __test__ = False

    cloning: str = "pending"  # pending | in_progress | completed | failed
    analyzing: str = "pending"
    building: str = "pending"
    starting: str = "pending"
    ready: str = "pending"
    discovering: str = "pending"
    discovery_complete: str = "pending"
    testing: str = "pending"
    analyzing_failures: str = "pending"
    report: str = "pending"


class TestRunResponse(BaseModel):
    """Test run status and details."""
    __test__ = False

    id: str
    project_id: str
    branch: str
    commit_sha: str | None = None
    status: str
    failure_reason: str | None = None
    failure_stage: str | None = None
    cancellation_requested: bool = False
    discovery_enabled: bool = False
    testing_enabled: bool = False
    detected_config: dict | None = None
    progress: TestRunProgress | None = None

    # Stats
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0

    # AI health and result status
    ai_status: str | None = None
    ai_model: str | None = None
    ai_test_count: int = 0
    ai_warning: str | None = None
    static_findings: dict | None = None
    observations: list[dict] | None = None

    # Timestamps
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestRunListResponse(BaseModel):
    """List of test runs."""

    runs: list[TestRunResponse]
    total: int
