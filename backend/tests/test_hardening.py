"""Regression coverage for Phase 1 lifecycle, persistence and configuration."""
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.config import APP_ROOT, Settings
from app.models.project import Project
from app.models.test_run import TestRun as Run, TestRunStatus as S
from app.models.log import Log
from app.schemas.common import ExecutionResult, HealthCheckResult, SandboxConfig
from app.services.github_service import GitHubService
from app.services.project_detector import detect_project, DetectionError
from app.services.sandbox_manager import SandboxManager
from app.worker.control import RunControl, RunCancelled, RunDeadlineExceeded
from app.worker.pipeline import Pipeline, InvalidTransition


async def new_run(db):
    project = Project(repository_url="https://github.com/test/fixture")
    db.add(project)
    await db.flush()
    run = Run(project=project, status=S.QUEUED, branch="", progress={"cloning": "pending"})
    db.add(run)
    await db.commit()
    return run


class FixtureGit(GitHubService):
    def clone_repository(self, repository_url, branch=None, target_dir=None):
        self.control.check()
        target_dir.mkdir(parents=True)
        (target_dir / "package.json").write_text(json.dumps({"scripts": {"start": "node server.js", "build": "node build.js"}}))
        return {"repo_path": str(target_dir), "branch": "trunk", "commit_sha": "a" * 40}


class FakeSandbox:
    def __init__(self, control, run_id, fail=None):
        self.control, self.fail = control, fail
        self.owned = set()
        self.client = MagicMock()

    def image_exists(self, image):
        return True

    def create(self, config, repo):
        self.owned.add("container")
        if self.fail == "copy":
            raise RuntimeError("copy failed")
        return {"container_id": "container"}

    def execute(self, container_id, command, source=None, **kwargs):
        self.control.check()
        if self.fail == "unexpected":
            raise RuntimeError("unexpected exception")
        if self.fail == "deadline":
            self.control.deadline = time.monotonic() - 1
            self.control.check()
        if self.fail == "cancel":
            self.control.cancel()
            self.control.check()
        return ExecutionResult(command=command, exit_code=1 if self.fail == source else 0,
                               stderr="fixture error" if self.fail == source else "")

    def execute_detached(self, *args, **kwargs):
        if self.fail == "startup":
            raise RuntimeError("startup failed")
        return "exec"

    def restrict_network(self, container_id):
        self.control.check()

    def kill(self, container_id):
        pass

    def collect_logs(self, container_id):
        return [("application", "stdout", "app stdout"), ("application", "stderr", "app stderr")]

    def cleanup(self):
        self.owned.clear()


@pytest.mark.parametrize("failure,expected", [
    (None, S.READY), ("copy", S.FAILED), ("install", S.FAILED),
    ("build", S.FAILED), ("startup", S.FAILED), ("unexpected", S.FAILED),
    ("deadline", S.FAILED), ("cancel", S.CANCELLED),
])
async def test_pipeline_cleanup_all_paths(db, tmp_path, failure, expected):
    run = await new_run(db)
    control = RunControl(30)
    sandbox = FakeSandbox(control, run.id, failure)
    pipeline = Pipeline(db, control, lambda *args: sandbox, FixtureGit(tmp_path))
    pipeline.health_checker.check_sandbox = AsyncMock(return_value=HealthCheckResult(is_healthy=True, url="local", status_code=200))
    await pipeline.run(run)
    await db.refresh(run)
    assert run.status == expected
    assert run.finished_at is not None
    assert not sandbox.owned
    assert not (tmp_path / run.id).exists()
    assert run.container_id is None
    if failure != "copy":
        messages = [row.message for row in (await db.execute(select(Log))).scalars()]
        assert any("app stdout" in text for text in messages)
        assert any("app stderr" in text for text in messages)


async def test_invalid_transition_and_json_persistence(db):
    run = await new_run(db)
    pipeline = Pipeline(db)
    with pytest.raises(InvalidTransition):
        await pipeline._update_status(run, S.READY)
    assert run.status == S.QUEUED
    await pipeline._update_status(run, S.CLONING)
    await pipeline._update_status(run, S.ANALYZING)
    db.expire(run, ["progress"])
    await db.refresh(run, ["progress"])
    assert run.progress == {"cloning": "completed", "analyzing": "in_progress"}
    await pipeline._update_status(run, S.CANCELLED)
    with pytest.raises(InvalidTransition):
        await pipeline._update_status(run, S.READY)


async def test_persisted_cancel_prevents_transition(db):
    run = await new_run(db)
    run.cancellation_requested = True
    await db.commit()
    pipeline = Pipeline(db)
    with pytest.raises(RunCancelled):
        await pipeline._update_status(run, S.CLONING)
    assert run.status == S.QUEUED


def test_config_independent_of_cwd(tmp_path, monkeypatch):
    first = Settings(_env_file=None, database_url="sqlite:///data/test.db", workspaces_dir="runs", evidence_dir="evidence")
    monkeypatch.chdir(tmp_path)
    second = Settings(_env_file=None, database_url="sqlite:///data/test.db", workspaces_dir="runs", evidence_dir="evidence")
    assert first.database_url == second.database_url
    assert first.database_url.startswith("sqlite+aiosqlite:///")
    assert Path(first.workspaces_dir) == APP_ROOT / "runs"
    assert first.evidence_dir == second.evidence_dir


def test_sandbox_security_and_partial_creation_cleanup(monkeypatch, tmp_path):
    client = MagicMock()
    container = client.containers.create.return_value
    container.id, container.short_id, container.ports = "id", "short", {}
    client.containers.get.return_value = container
    monkeypatch.setattr("app.services.sandbox_manager.docker.from_env", lambda **kwargs: client)
    manager = SandboxManager()
    monkeypatch.setattr(manager, "_copy_repo", MagicMock(side_effect=RuntimeError("copy failed")))
    with pytest.raises(RuntimeError, match="copy failed"):
        manager.create(SandboxConfig(image="test"), tmp_path)
    config = client.containers.create.call_args.kwargs
    assert config["user"] == "10001:10001"
    assert config["privileged"] is False
    assert config["cap_drop"] == ["ALL"]
    assert config["security_opt"] == ["no-new-privileges"]
    assert config["pids_limit"] == 256
    assert config["nano_cpus"] > 0
    assert config["mem_limit"] == config["memswap_limit"] == "2g"
    assert "volumes" not in config
    assert config["ports"] == {}
    container.remove.assert_called_once_with(force=True, v=True)
    assert not manager.owned


def test_command_timeout_kills_before_return(monkeypatch):
    client = MagicMock()
    client.api.exec_inspect.return_value = {"Running": True}
    monkeypatch.setattr("app.services.sandbox_manager.docker.from_env", lambda **kwargs: client)
    sandbox = SandboxManager()
    monkeypatch.setattr(sandbox, "_launch", lambda *args: ("exec", "out", "err"))
    monkeypatch.setattr(sandbox, "read_file", lambda *args: "retained")
    monkeypatch.setattr(sandbox, "kill", MagicMock())
    result = sandbox.execute("id", "sleep 60", timeout=0.01)
    sandbox.kill.assert_called_once_with("id")
    assert result.timed_out and result.exit_code == 124
    assert result.stdout == "retained"


def test_custom_port_and_nested_app(tmp_path):
    app = tmp_path / "apps" / "web"
    app.mkdir(parents=True)
    (app / "package.json").write_text(json.dumps({"scripts": {"start": "PORT=4321 node server.js"}}))
    config = detect_project(tmp_path)
    assert config.project_dir == "apps/web" and config.expected_port == 4321
    other = tmp_path / "other"
    other.mkdir()
    (other / "package.json").write_text((app / "package.json").read_text())
    with pytest.raises(DetectionError, match="Ambiguous"):
        detect_project(tmp_path)
    (tmp_path / "testq.json").write_text(json.dumps({"project_dir": "apps/web", "port": 4322}))
    assert detect_project(tmp_path).expected_port == 4322


def test_project_selection_cannot_escape(tmp_path):
    (tmp_path / "testq.json").write_text('{"project_dir":"../outside"}')
    with pytest.raises(DetectionError, match="escapes"):
        detect_project(tmp_path)

async def test_sqlite_additive_migration(tmp_path, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app import database
    path = tmp_path / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as connection:
        # Deliberately minimal legacy table: migration must preserve its record.
        await connection.execute(text("CREATE TABLE test_runs (id TEXT PRIMARY KEY, status TEXT)"))
        await connection.execute(text("INSERT INTO test_runs VALUES ('existing', 'READY')"))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database.settings, "database_url", f"sqlite+aiosqlite:///{path.as_posix()}")
    await database.init_db()
    await database.init_db()  # idempotent
    async with engine.connect() as connection:
        row = (await connection.execute(text("SELECT id, status, cancellation_requested, discovery_enabled FROM test_runs"))).one()
        assert tuple(row) == ("existing", "READY", 0, 0)
    await engine.dispose()


async def test_clone_failure_cleanup(db, tmp_path):
    run = await new_run(db)
    github = FixtureGit(tmp_path)
    def failed_clone(*args, target_dir=None, **kwargs):
        target_dir.mkdir()
        (target_dir / "partial").write_text("partial clone")
        raise RuntimeError("clone failed")
    github.clone_repository = failed_clone
    factory = MagicMock()
    await Pipeline(db, github=github, sandbox_factory=factory).run(run)
    factory.assert_not_called()
    assert run.status == S.FAILED and run.failure_stage == "CLONING"
    assert not (tmp_path / run.id).exists()


async def test_external_task_cancellation_joins_worker(db, tmp_path):
    import threading
    run = await new_run(db)
    control = RunControl(30)
    sandbox = FakeSandbox(control, run.id)
    started = threading.Event()
    stopped = threading.Event()
    def long_execute(*args, **kwargs):
        started.set()
        try:
            while True:
                control.check()
                time.sleep(0.01)
        finally:
            stopped.set()
    sandbox.execute = long_execute
    pipeline = Pipeline(db, control, lambda *args: sandbox, FixtureGit(tmp_path))
    task = asyncio.create_task(pipeline.run(run))
    while not started.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.wait_for(task, 5)
    assert stopped.is_set()
    assert run.status == S.CANCELLED
    assert not sandbox.owned


async def test_recovery_cleans_before_cancel_commit(db, tmp_path, monkeypatch):
    from app.worker import recovery
    run = await new_run(db)
    run.cancellation_requested = True
    await db.commit()
    sandbox = MagicMock()
    monkeypatch.setattr(recovery, "SandboxManager", lambda: sandbox)
    monkeypatch.setattr(recovery, "GitHubService", lambda: GitHubService(tmp_path))
    await recovery.recover_run(db, run)
    sandbox.adopt_run.assert_called_once_with(run.id)
    sandbox.cleanup.assert_called_once()
    assert run.status == S.CANCELLED and run.finished_at


def test_cleanup_failure_is_not_suppressed(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("app.services.sandbox_manager.docker.from_env", lambda **kwargs: client)
    sandbox = SandboxManager()
    sandbox.owned.add("owned")
    client.containers.get.return_value.remove.side_effect = RuntimeError("daemon unavailable")
    from app.services.sandbox_manager import SandboxError
    with pytest.raises(SandboxError, match="Cleanup failed"):
        sandbox.cleanup()
    assert "owned" in sandbox.owned
    assert client.containers.get.return_value.remove.call_count == 3
