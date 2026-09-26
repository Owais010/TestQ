"""TestRun ORM Model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TestRunStatus:
    """Valid test run states. Acts as a state machine."""

    QUEUED = "QUEUED"
    CLONING = "CLONING"
    ANALYZING = "ANALYZING"
    BUILDING = "BUILDING"
    STARTING = "STARTING"
    READY = "READY"
    DISCOVERING = "DISCOVERING"
    DISCOVERY_COMPLETE = "DISCOVERY_COMPLETE"
    TESTING = "TESTING"
    ANALYZING_FAILURES = "ANALYZING_FAILURES"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    TERMINAL = {FAILED, CANCELLED, COMPLETED, DISCOVERY_COMPLETE}

    ALL = {
        QUEUED, CLONING, ANALYZING, BUILDING, STARTING,
        READY, TESTING, ANALYZING_FAILURES, COMPLETED,
        FAILED, CANCELLED, DISCOVERING, DISCOVERY_COMPLETE,
    }

    # Valid transitions: current_state -> set of allowed next states
    TRANSITIONS = {
        QUEUED: {CLONING, FAILED, CANCELLED},
        CLONING: {ANALYZING, FAILED, CANCELLED},
        ANALYZING: {BUILDING, FAILED, CANCELLED},
        BUILDING: {STARTING, FAILED, CANCELLED},
        STARTING: {READY, FAILED, CANCELLED},
        READY: {DISCOVERING, TESTING, FAILED, CANCELLED},
        DISCOVERING: {DISCOVERY_COMPLETE, TESTING, FAILED, CANCELLED},
        DISCOVERY_COMPLETE: set(),
        TESTING: {ANALYZING_FAILURES, COMPLETED, FAILED, CANCELLED},
        ANALYZING_FAILURES: {COMPLETED, FAILED, CANCELLED},
        COMPLETED: set(),
        FAILED: set(),
        CANCELLED: set(),
    }


class TestRun(Base):
    """A single test run against a project."""

    __tablename__ = "test_runs"
    __test__ = False

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    branch: Mapped[str] = mapped_column(String(100), default="main")
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default=TestRunStatus.QUEUED, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discovery_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    testing_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Detection results
    detected_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Progress tracking
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Summary stats (populated as run progresses)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)

    # AI health and result status
    ai_status: Mapped[str | None] = mapped_column(String(30), nullable=True, default="NOT_REQUESTED")
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_test_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    static_findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observations: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Sandbox info
    container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sandbox_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    project = relationship("Project", back_populates="test_runs", lazy="selectin")
    logs = relationship("Log", back_populates="test_run", lazy="selectin")

    def can_transition_to(self, new_status: str) -> bool:
        """Check if the state transition is valid."""
        return new_status in TestRunStatus.TRANSITIONS.get(self.status, set())

    def __repr__(self) -> str:
        return f"<TestRun {self.id[:8]} status={self.status}>"
