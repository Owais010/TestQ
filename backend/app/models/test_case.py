"""Phase 3 persistence: test definitions, results and evidence linkage."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TestCase(Base):
    """A structured deterministic test definition associated with a test run."""
    __tablename__ = "test_cases"
    __test__ = False

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # "ui" or "api"
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    source: Mapped[str] = mapped_column(String(20), default="baseline", server_default="baseline")
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        tid = (self.id or "")[:8]
        return f"<TestCase {tid} {self.type} {self.title[:40]}>"


class TestResult(Base):
    """Result of executing a single deterministic test case."""
    __tablename__ = "test_results"
    __test__ = False

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # PASS, FAIL, ERROR, TIMEOUT, CANCELLED
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    expected: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actual: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assertions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reproduction_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reproduction_total: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        rid = (self.id or "")[:8]
        return f"<TestResult {rid} status={self.status}>"
