"""TestRun API schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class TestRunCreate(BaseModel):
    """Request to create and start a test run."""

    repository_url: str = Field(
        ...,
        description="GitHub repository URL",
        examples=["https://github.com/user/project"],
    )
    branch: str = Field("main", description="Branch to test")


class TestRunProgress(BaseModel):
    """Real-time progress of a test run's pipeline stages."""

    cloning: str = "pending"  # pending | in_progress | completed | failed
    analyzing: str = "pending"
    building: str = "pending"
    starting: str = "pending"
    ready: str = "pending"
    testing: str = "pending"
    analyzing_failures: str = "pending"
    report: str = "pending"


class TestRunResponse(BaseModel):
    """Test run status and details."""

    id: str
    project_id: str
    branch: str
    commit_sha: str | None = None
    status: str
    failure_reason: str | None = None
    failure_stage: str | None = None
    detected_config: dict | None = None
    progress: TestRunProgress | None = None

    # Stats
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0

    # Timestamps
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestRunListResponse(BaseModel):
    """List of test runs."""

    runs: list[TestRunResponse]
    total: int
