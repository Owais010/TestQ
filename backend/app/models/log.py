"""Log ORM Model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Log(Base):
    """A log entry associated with a test run."""

    __tablename__ = "logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_runs.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "build", "startup", "sandbox", "system"
    level: Mapped[str] = mapped_column(
        String(10), default="INFO"
    )  # DEBUG, INFO, WARNING, ERROR
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    test_run = relationship("TestRun", back_populates="logs")

    def __repr__(self) -> str:
        return f"<Log {self.source} {self.level}: {self.message[:50]}>"
