"""
Database model for persisted AI Failure Analyses (Phase 4.5).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FailureAnalysisRecord(Base):
    """Persisted structured AI failure analysis linked to a test result."""
    __tablename__ = "failure_analyses"
    __test__ = False

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id"), nullable=False, index=True
    )
    test_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_results.id"), nullable=False, unique=True, index=True
    )
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    likely_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_steps: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_references: Mapped[list] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    reproduction_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reproduction_total: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    classification: Mapped[str] = mapped_column(
        String(30), default="POSSIBLE BUG", server_default="POSSIBLE BUG"
    )  # CONFIRMED BUG, POSSIBLE BUG, TEST FAILURE, ENVIRONMENT FAILURE
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        fid = (self.id or "")[:8]
        return f"<FailureAnalysisRecord {fid} [{self.severity}] {self.title[:30]}>"
