"""
TestQ Database Setup.

SQLite with SQLAlchemy async engine.
Schema designed for straightforward migration to PostgreSQL later.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from pathlib import Path

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def init_db():
    """Create tables and apply idempotent additive SQLite migrations."""
    # Import all models so create_all creates Phase 3 and Phase 4.5 tables.
    import app.models.test_case  # noqa: F401
    import app.models.failure_analysis  # noqa: F401

    url = make_url(settings.database_url)
    if url.drivername.startswith("sqlite") and url.database not in (None, ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.run_sync(lambda c: {
            col["name"] for col in inspect(c).get_columns("test_runs")
        })
        if "cancellation_requested" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN cancellation_requested BOOLEAN NOT NULL DEFAULT 0"
            ))
        if "discovery_enabled" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN discovery_enabled BOOLEAN NOT NULL DEFAULT 0"
            ))
        if "testing_enabled" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN testing_enabled BOOLEAN NOT NULL DEFAULT 0"
            ))
        if "ai_status" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN ai_status VARCHAR(30) DEFAULT 'NOT_REQUESTED'"
            ))
        if "ai_model" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN ai_model VARCHAR(100)"
            ))
        if "ai_test_count" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN ai_test_count INTEGER DEFAULT 0"
            ))
        if "ai_warning" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN ai_warning TEXT"
            ))
        if "static_findings" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN static_findings JSON"
            ))
        if "observations" not in columns:
            await conn.execute(text(
                "ALTER TABLE test_runs ADD COLUMN observations JSON"
            ))

        # Check test_results columns
        tr_columns = await conn.run_sync(lambda c: {
            col["name"] for col in inspect(c).get_columns("test_results")
        } if inspect(c).has_table("test_results") else set())
        if "http_status" not in tr_columns and tr_columns:
            await conn.execute(text("ALTER TABLE test_results ADD COLUMN http_status INTEGER"))
        if "reproduction_count" not in tr_columns and tr_columns:
            await conn.execute(text("ALTER TABLE test_results ADD COLUMN reproduction_count INTEGER DEFAULT 1"))
        if "reproduction_total" not in tr_columns and tr_columns:
            await conn.execute(text("ALTER TABLE test_results ADD COLUMN reproduction_total INTEGER DEFAULT 1"))
        if "confirmed" not in tr_columns and tr_columns:
            await conn.execute(text("ALTER TABLE test_results ADD COLUMN confirmed BOOLEAN DEFAULT 0"))

        # Check failure_analyses columns
        fa_columns = await conn.run_sync(lambda c: {
            col["name"] for col in inspect(c).get_columns("failure_analyses")
        } if inspect(c).has_table("failure_analyses") else set())
        if "reproduction_count" not in fa_columns and fa_columns:
            await conn.execute(text("ALTER TABLE failure_analyses ADD COLUMN reproduction_count INTEGER DEFAULT 1"))
        if "reproduction_total" not in fa_columns and fa_columns:
            await conn.execute(text("ALTER TABLE failure_analyses ADD COLUMN reproduction_total INTEGER DEFAULT 1"))
        if "classification" not in fa_columns and fa_columns:
            await conn.execute(text("ALTER TABLE failure_analyses ADD COLUMN classification VARCHAR(50) DEFAULT 'POSSIBLE BUG'"))

        # Phase 3: add test_result_id to evidence (nullable FK, additive).
        evidence_columns = await conn.run_sync(lambda c: {
            col["name"] for col in inspect(c).get_columns("evidence")
        } if inspect(c).has_table("evidence") else set())
        if "test_result_id" not in evidence_columns and evidence_columns:
            await conn.execute(text(
                "ALTER TABLE evidence ADD COLUMN test_result_id VARCHAR(36) REFERENCES test_results(id)"
            ))


async def get_db() -> AsyncSession:
    """Dependency that yields a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
