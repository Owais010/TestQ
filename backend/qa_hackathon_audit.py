"""Independent live-model audit; writes only to evidence/hackathon-audit/."""
import asyncio
import json
import logging
import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "hackathon-audit"
OUT.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (OUT / "audit.db").as_posix()
os.environ["EVIDENCE_DIR"] = str(OUT / "artifacts")
os.environ["WORKSPACES_DIR"] = str(OUT / "workspaces")

from sqlalchemy import select
from app.database import init_db, async_session
from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_case import TestCase, TestResult
from app.models.failure_analysis import FailureAnalysisRecord
from app.models.log import Log
from app.models.discovery import Evidence, DiscoverySession
from app.worker.pipeline import Pipeline
from tests.test_docker_hardening import LocalGit

async def main():
    logging.basicConfig(level=logging.INFO)
    source = OUT / "demo_source.git"
    if not source.exists():
        shutil.copytree(ROOT / "demo", source, ignore=shutil.ignore_patterns("node_modules", ".git"))
        for args in (["init", "-b", "main"], ["add", "."],
                     ["-c", "user.name=TestQ Audit", "-c", "user.email=audit@example.invalid", "commit", "-m", "Local audit fixture"]):
            subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    await init_db()
    async with async_session() as db:
        project = Project(repository_url="https://github.com/testq-audit/local-demo")
        db.add(project)
        await db.flush()
        run = TestRun(project=project, status=TestRunStatus.QUEUED, branch="",
                      discovery_enabled=True, testing_enabled=True, progress={})
        db.add(run)
        await db.commit()
        print("AUDIT_RUN=" + run.id, flush=True)
        await Pipeline(db, github=LocalGit(OUT / "clones", source)).run(run)
        await db.refresh(run)
        cases = (await db.execute(select(TestCase).where(TestCase.run_id == run.id))).scalars().all()
        results = (await db.execute(select(TestResult).where(TestResult.run_id == run.id))).scalars().all()
        findings = (await db.execute(select(FailureAnalysisRecord).where(FailureAnalysisRecord.run_id == run.id))).scalars().all()
        logs = (await db.execute(select(Log).where(Log.run_id == run.id))).scalars().all()
        evidence = (await db.execute(select(Evidence).where(Evidence.run_id == run.id))).scalars().all()
        discoveries = (await db.execute(select(DiscoverySession).where(DiscoverySession.run_id == run.id))).scalars().all()
        def row(obj):
            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        payload = {"run": row(run), "cases": list(map(row, cases)),
                   "results": list(map(row, results)), "findings": list(map(row, findings)),
                   "logs": list(map(row, logs)), "evidence": list(map(row, evidence)),
                   "discovery": list(map(row, discoveries))}
        (OUT / "live-demo.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"status": run.status, "failure": run.failure_reason,
            "tests": len(cases), "ai_tests": sum(c.source == "ai" for c in cases),
            "outcomes": [r.status for r in results], "findings": len(findings),
            "evidence": len(evidence), "container_id": run.container_id}), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
