"""Run API. Single-process background work with explicit cancellation signalling."""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, async_session
from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.log import Log
from app.schemas.test_run import TestRunCreate, TestRunResponse, TestRunListResponse
from app.services.github_service import GitHubService, InvalidRepositoryURL
from app.worker.control import RunControl, controls

logger = logging.getLogger("testq.api.test_runs")
router = APIRouter(prefix="/api/test-runs", tags=["test-runs"])


async def _run_pipeline(run_id):
    from sqlalchemy.orm import selectinload
    from app.worker.pipeline import Pipeline
    control = controls.setdefault(run_id, RunControl(settings.run_timeout))
    try:
        async with async_session() as db:
            stmt = select(TestRun).where(TestRun.id == run_id).options(selectinload(TestRun.project))
            run = (await db.execute(stmt)).scalar_one_or_none()
            if run and run.status not in S.TERMINAL:
                await Pipeline(db, control=control).run(run)
    except Exception:
        logger.exception("Background pipeline failed for %s", run_id)
        raise
    finally:
        control.done.set()
        controls.pop(run_id, None)


@router.post("", response_model=TestRunResponse, status_code=201)
async def create_test_run(data: TestRunCreate, background_tasks: BackgroundTasks,
                          db: AsyncSession = Depends(get_db)):
    try:
        url = GitHubService().validate_url(data.repository_url)
    except InvalidRepositoryURL as error:
        raise HTTPException(status_code=400, detail=str(error))
    if data.testing_enabled and not data.discover:
        raise HTTPException(status_code=400, detail="Testing requires discovery to be enabled")
    project = (await db.execute(select(Project).where(Project.repository_url == url))).scalar_one_or_none()
    if not project:
        project = Project(repository_url=url, default_branch=data.branch or "")
        db.add(project)
        await db.flush()
    run = TestRun(project_id=project.id, branch=data.branch or "", status=S.QUEUED,
                  discovery_enabled=data.discover,
                  testing_enabled=data.testing_enabled,
                  progress={key: "pending" for key in (
                      "cloning", "analyzing", "building", "starting", "ready",
                      "discovering", "testing", "analyzing_failures", "report")})
    db.add(run)
    await db.commit()
    await db.refresh(run)
    controls[run.id] = RunControl(settings.run_timeout)
    background_tasks.add_task(_run_pipeline, run.id)
    return run


@router.get("", response_model=TestRunListResponse)
@router.get("/", response_model=TestRunListResponse, include_in_schema=False)
async def list_test_runs(
    limit: int = 10,
    offset: int = 0,
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(TestRun)
    if project_id:
        query = query.where(TestRun.project_id == project_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    runs_query = query.order_by(TestRun.created_at.desc()).offset(offset).limit(limit)
    runs = (await db.execute(runs_query)).scalars().all()

    return TestRunListResponse(runs=list(runs), total=total)


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@router.post("/{run_id}/cancel", response_model=TestRunResponse)
async def cancel_test_run(run_id: str, response: Response, db: AsyncSession = Depends(get_db)):
    run = await get_test_run(run_id, db)
    if run.status in S.TERMINAL or run.finished_at:
        raise HTTPException(status_code=400, detail=f"Cannot cancel finished run: {run.status}")
    # Conditional write prevents racing a completed worker. Persist BEFORE signalling.
    result = await db.execute(update(TestRun).where(
        TestRun.id == run_id, TestRun.finished_at.is_(None),
        TestRun.status.not_in(S.TERMINAL),
    ).values(cancellation_requested=True).execution_options(synchronize_session=False))
    await db.commit()
    if not result.rowcount:
        raise HTTPException(status_code=409, detail="Run finished while cancellation was requested")
    control = controls.get(run_id)
    if control:
        control.cancel()
        # Worker owns kill -> log export -> removal -> final CANCELLED commit.
        try:
            await asyncio.wait_for(control.done.wait(), timeout=5)
        except asyncio.TimeoutError:
            response.status_code = 202
    else:
        # Interrupted run in the supported single-process deployment.
        # Refresh the request flag before deciding its final state.
        await db.refresh(run)
        from app.worker.recovery import recover_run
        try:
            await recover_run(db, run)
        except Exception as error:
            logger.exception("Orphan cleanup failed for %s", run_id)
            raise HTTPException(status_code=503, detail="Cancellation requested; sandbox cleanup needs retry") from error
    await db.refresh(run)
    return run


@router.get("/{run_id}/logs")
async def get_test_run_logs(run_id: str, source: str | None = None, level: str | None = None,
                            db: AsyncSession = Depends(get_db)):
    await get_test_run(run_id, db)
    query = select(Log).where(Log.run_id == run_id)
    if source:
        query = query.where(Log.source == source)
    if level:
        query = query.where(Log.level == level)
    logs = (await db.execute(query.order_by(Log.timestamp))).scalars().all()
    return {"run_id": run_id, "logs": [
        {"id": log.id, "source": log.source, "level": log.level,
         "message": log.message, "timestamp": log.timestamp.isoformat()}
        for log in logs], "total": len(logs)}
