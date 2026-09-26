"""Recovery for the documented single-backend-process deployment."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.log import Log
from app.services.sandbox_manager import SandboxManager
from app.services.github_service import GitHubService


async def recover_run(db, run):
    """Do not report terminal cancellation until orphan cleanup succeeds."""
    sandbox = await asyncio.to_thread(SandboxManager)
    await asyncio.to_thread(sandbox.adopt_run, run.id)
    await asyncio.to_thread(sandbox.cleanup)
    github = GitHubService()
    await asyncio.to_thread(github.cleanup_workspace, github.workspaces_dir / run.id)
    terminal = S.CANCELLED if run.cancellation_requested else S.FAILED
    if not run.can_transition_to(terminal):
        raise ValueError(f"Cannot recover run in {run.status}")
    run.status = terminal
    run.failure_reason = "Cancelled by user" if terminal == S.CANCELLED else "Backend stopped before run finished"
    run.failure_stage = "RECOVERY"
    run.finished_at = datetime.now(timezone.utc)
    run.container_id = None
    run.sandbox_port = None
    run.progress = {key: terminal.lower() if value == "in_progress" else value
                    for key, value in (run.progress or {}).items()}
    db.add(Log(run_id=run.id, source="system", level="ERROR", message=run.failure_reason))
    await db.commit()


async def recover_interrupted_runs():
    async with async_session() as db:
        runs = (await db.execute(select(TestRun).where(
            TestRun.finished_at.is_(None), TestRun.status.not_in(S.TERMINAL)
        ))).scalars().all()
        for run in runs:
            await recover_run(db, run)
