"""Project ORM Model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    """A GitHub project that TestQ has analyzed."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    repository_url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    detected_framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_package_manager: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    project_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    test_runs = relationship("TestRun", back_populates="project", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Project {self.id[:8]} {self.repository_url}>"
