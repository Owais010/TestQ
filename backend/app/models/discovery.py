"""Minimal Phase 2 persistence: a validated map plus independently verified artifacts."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DiscoverySession(Base):
    __tablename__ = "discovery_sessions"
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"),unique=True,index=True)
    status: Mapped[str] = mapped_column(String(20),default="running")
    application_map: Mapped[dict] = mapped_column(JSON,nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"),index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("discovery_sessions.id"),index=True)
    test_result_id: Mapped[str | None] = mapped_column(String(36),nullable=True,index=True)
    page_url: Mapped[str | None] = mapped_column(String(2000),nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    path: Mapped[str] = mapped_column(String(500),unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))

