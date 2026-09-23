"""
Test Runs API routes.

Handles creating, retrieving, and cancelling test runs.
POST /api/test-runs dispatches to the background worker pipeline.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus
from app.models.log import Log
from app.schemas.test_run import TestRunCreate, TestRunResponse
from app.services.github_service import GitHubService, InvalidRepositoryURL

logger = logging.getLogger("testq.api.test_runs")

router = APIRouter(prefix="/api/test-runs", tags=["test-runs"])


async def _run_pipeline(run_id: str) -> None:
    """Background task that executes the test pipeline."""
    from app.worker.pipeline import Pipeline

    async with async_session() as db:
        try:
            result = await db.execute(
                select(TestRun).where(TestRun.id == run_id)
            )
            test_run = result.scalar_one_or_none()
            if not test_run:
                logger.error(f"Test run not found: {run_id}")
                return

            pipeline = Pipeline(db)
            await pipeline.run(test_run)

        except Exception as e:
            logger.error(f"Pipeline background task failed: {e}", exc_info=True)
            # Try to mark as failed
            try:
                result = await db.execute(
                    select(TestRun).where(TestRun.id == run_id)
                )
                test_run = result.scalar_one_or_none()
                if test_run and test_run.status not in (
                    TestRunStatus.FAILED, TestRunStatus.COMPLETED
                ):
                    test_run.status = TestRunStatus.FAILED
                    test_run.failure_reason = f"Internal error: {str(e)}"
                    test_run.finished_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception:
                pass


@router.post("", response_model=TestRunResponse, status_code=201)
async def create_test_run(
    data: TestRunCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Create and start a new test run.

    1. Validates the repository URL
    2. Creates or finds the project
    3. Creates a test run record (QUEUED)
    4. Dispatches the pipeline to a background worker
    5. Returns immediately with the run ID
    """
    # Validate URL
    github = GitHubService()
    try:
        validated_url = github.validate_url(data.repository_url)
    except InvalidRepositoryURL as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Find or create project
    result = await db.execute(
        select(Project).where(Project.repository_url == validated_url)
    )
    project = result.scalar_one_or_none()

    if not project:
        project = Project(
            repository_url=validated_url,
            default_branch=data.branch,
        )
        db.add(project)
        await db.flush()

    # Create test run
    test_run = TestRun(
        project_id=project.id,
        branch=data.branch,
        status=TestRunStatus.QUEUED,
        progress={
            "cloning": "pending",
            "analyzing": "pending",
            "building": "pending",
            "starting": "pending",
            "ready": "pending",
            "testing": "pending",
            "analyzing_failures": "pending",
            "report": "pending",
        },
    )
    db.add(test_run)
    await db.commit()
    await db.refresh(test_run)

    logger.info(f"Created test run {test_run.id[:8]} for {validated_url}")

    # Dispatch pipeline to background
    background_tasks.add_task(_run_pipeline, test_run.id)

    return test_run


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get test run status and details."""
    result = await db.execute(
        select(TestRun).where(TestRun.id == run_id)
    )
    test_run = result.scalar_one_or_none()
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return test_run


@router.post("/{run_id}/cancel", response_model=TestRunResponse)
async def cancel_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Cancel an active test run."""
    result = await db.execute(
        select(TestRun).where(TestRun.id == run_id)
    )
    test_run = result.scalar_one_or_none()
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    if test_run.status in (TestRunStatus.COMPLETED, TestRunStatus.FAILED, TestRunStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel run in state: {test_run.status}",
        )

    test_run.status = TestRunStatus.CANCELLED
    test_run.finished_at = datetime.now(timezone.utc)
    test_run.failure_reason = "Cancelled by user"

    # Try to destroy sandbox container if it exists
    if test_run.container_id:
        try:
            import asyncio
            from app.services.sandbox_manager import SandboxManager
            sandbox = SandboxManager()
            await asyncio.to_thread(sandbox.destroy, test_run.container_id)
        except Exception as e:
            logger.warning(f"Failed to destroy sandbox on cancel: {e}")

    await db.commit()
    return test_run


@router.get("/{run_id}/logs")
async def get_test_run_logs(
    run_id: str,
    source: str | None = None,
    level: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get logs for a test run, optionally filtered by source and level."""
    # Verify run exists
    result = await db.execute(
        select(TestRun).where(TestRun.id == run_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Test run not found")

    query = select(Log).where(Log.run_id == run_id)
    if source:
        query = query.where(Log.source == source)
    if level:
        query = query.where(Log.level == level)
    query = query.order_by(Log.timestamp)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "run_id": run_id,
        "logs": [
            {
                "id": log.id,
                "source": log.source,
                "level": log.level,
                "message": log.message,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in logs
        ],
        "total": len(logs),
    }
