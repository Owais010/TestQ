"""Opt-in real Docker tests; clone local git fixtures through the actual pipeline."""
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import docker
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.project import Project
from app.models.test_run import TestRun as Run, TestRunStatus as S
from app.models.log import Log
from app.services.github_service import GitHubService
from app.services.sandbox_manager import SandboxManager
from app.schemas.common import SandboxConfig
from app.worker.control import RunControl, RunDeadlineExceeded
from app.worker.pipeline import Pipeline

pytestmark = [pytest.mark.docker, pytest.mark.skipif(
    os.environ.get("TESTQ_DOCKER_TESTS") != "1", reason="Set TESTQ_DOCKER_TESTS=1 for real Docker tests")]


def git_fixture(root, mode):
    source = root / "source.git"
    source.mkdir()
    if mode == "python":
        (source / "requirements.txt").write_text("fastapi==0.115.12\nuvicorn==0.34.2\n")
        (source / "main.py").write_text(
            "import os\nfrom fastapi import FastAPI\napp=FastAPI()\n"
            "print('APP-STDOUT uid='+str(os.getuid()), flush=True)\n"
            "@app.get('/')\ndef home(): return {'ok': True}\n")
    else:
        helper = source / "dev-tool"
        helper.mkdir()
        (helper / "package.json").write_text('{"name":"build-helper","version":"1.0.0","main":"index.js"}')
        (helper / "index.js").write_text("module.exports = 'BUILD-OK';")
        scripts = {"start": "node server.js", "build": "node build.js"}
        if mode == "install":
            scripts["postinstall"] = 'node -e "console.error(\'INSTALL-FAIL\');process.exit(7)"'
        (source / "package.json").write_text(json.dumps({"name": "fixture", "version": "1.0.0",
            "scripts": scripts, "devDependencies": {"build-helper": "file:./dev-tool"}}))
        build = "console.log(require('build-helper'));"
        if mode == "build":
            build += "console.error('BUILD-FAIL'); process.exit(8);"
        if mode in ("cancel", "deadline", "timeout"):
            build += "console.log('BUILD-WAITING'); setInterval(()=>{},1000);"
        (source / "build.js").write_text(build)
        server = """
const http = require('http');
const port = process.env.PORT || 4321;
console.log('APP-STDOUT uid=' + process.getuid() + ' env=' + process.env.NODE_ENV);
console.error('APP-STDERR');
http.createServer((req,res)=>{res.end('fixture');}).listen(port,'127.0.0.1');
"""
        if mode == "startup":
            server = "console.error('STARTUP-FAIL'); process.exit(9);"
        (source / "server.js").write_text(server)
    for args in (["init", "-b", "trunk"], ["add", "."],
                 ["-c", "user.name=TestQ", "-c", "user.email=testq@example.invalid", "commit", "-m", "fixture"]):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    return source


class LocalGit(GitHubService):
    """Only the source URL is substituted; real clone/branch/cleanup code runs."""
    def __init__(self, root, source):
        super().__init__(root)
        self.source = source

    def validate_url(self, url):
        return str(self.source)[:-4]


@pytest.mark.parametrize("mode,expected", [
    ("success", S.READY), ("python", S.READY), ("install", S.FAILED),
    ("build", S.FAILED), ("startup", S.FAILED), ("cancel", S.CANCELLED),
    ("deadline", S.FAILED),
    ("timeout", S.FAILED),
])
async def test_real_pipeline(tmp_path, monkeypatch, mode, expected):
    if mode == "timeout":
        monkeypatch.setattr(settings, "docker_timeout", 3)
    source = git_fixture(tmp_path, mode)
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'runs.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    client = docker.from_env()
    async def override_db():
        async with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    try:
        async with sessions() as db:
            project = Project(repository_url="https://github.com/test/fixture")
            db.add(project)
            await db.flush()
            run = Run(project=project, status=S.QUEUED, branch="", progress={})
            db.add(run)
            await db.commit()
            control = RunControl(180)
            pipeline = Pipeline(db, control=control, github=LocalGit(tmp_path / "clones", source))
            pipeline.health_checker.max_retries = 8
            pipeline.health_checker.retry_interval = 0.2
            task = asyncio.create_task(pipeline.run(run))
            if mode in ("cancel", "deadline"):
                # Wait for proof that an actual build process is running.
                for _ in range(400):
                    await asyncio.sleep(0.1)
                    if task.done():
                        break
                    if pipeline.sandbox:
                        logs = await asyncio.to_thread(pipeline.sandbox.collect_logs, run.container_id) if run.container_id else []
                        if any("BUILD-WAITING" in text for _, _, text in logs):
                            break
                else:
                    pytest.fail("Build did not start")
                assert not task.done(), run.failure_reason
                if mode == "cancel":
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
                        response = await api.post(f"/api/test-runs/{run.id}/cancel")
                        assert response.status_code in (200, 202), response.text
                        assert response.json()["cancellation_requested"]
                else:
                    control.deadline = time.monotonic() - 0.1
            await asyncio.wait_for(task, 180)
            await db.refresh(run)
            assert run.status == expected, run.failure_reason
            assert run.branch == "trunk" and run.commit_sha
            assert run.project.default_branch == "trunk"
            assert run.finished_at and run.container_id is None
            assert not (tmp_path / "clones" / run.id).exists()
            assert not client.containers.list(all=True, filters={"label": f"testq.run_id={run.id}"})
            messages = "\n".join(log.message for log in (await db.execute(select(Log).where(Log.run_id == run.id))).scalars())
            if mode in ("success", "python"):
                assert "APP-STDOUT uid=10001" in messages
                assert run.progress["ready"] == "completed"
            if mode == "success":
                assert "BUILD-OK" in messages and "APP-STDERR" in messages
                assert "env=production" in messages
            if mode in ("install", "build", "startup"):
                assert f"{mode.upper()}-FAIL" in messages
                assert run.failure_stage == ("STARTING" if mode == "startup" else "BUILDING")
            if mode == "deadline":
                assert "deadline" in run.failure_reason.lower()
            if mode == "timeout":
                assert "timed out" in run.failure_reason.lower()
                assert "BUILD-WAITING" in messages
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
                response = await api.get(f"/api/test-runs/{run.id}/logs")
                assert response.status_code == 200 and response.json()["total"] > 0
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        client.close()


def test_real_command_timeout_and_network():
    control = RunControl(60)
    sandbox = SandboxManager(control)
    container_id = None
    try:
        container_id = sandbox.create(SandboxConfig(image="testq-sandbox-node:latest", timeout=60))["container_id"]
        sandbox.restrict_network(container_id)
        container = sandbox.client.containers.get(container_id)
        container.reload()
        assert container.attrs["NetworkSettings"]["Networks"] == {}
        assert not container.attrs["Mounts"]
        host = container.attrs["HostConfig"]
        assert host["Privileged"] is False and host["PidsLimit"] == 256
        assert host["NanoCpus"] == 2_000_000_000
        assert host["Memory"] == host["MemorySwap"] == 2 * 1024**3
        assert "no-new-privileges" in host["SecurityOpt"]
        assert "ALL" in host["CapDrop"]
        assert container.attrs["Config"]["User"] == "10001:10001"
        result = sandbox.execute(container_id, "curl --noproxy '*' --connect-timeout 1 http://1.1.1.1", timeout=3)
        assert result.exit_code != 0
        begin = time.monotonic()
        result = sandbox.execute(container_id, "echo BEFORE-TIMEOUT; sleep 60 & wait", timeout=0.5)
        assert time.monotonic() - begin < 10
        assert result.timed_out and result.exit_code == 124
        assert "BEFORE-TIMEOUT" in result.stdout
        assert not sandbox.is_running(container_id)
    finally:
        sandbox.cleanup()
    assert not sandbox.client.containers.list(all=True, filters={"label": f"testq.run_id={sandbox.run_id}"})


def test_real_copy_failure_removes_created_container(tmp_path):
    sandbox = SandboxManager(RunControl(30))
    try:
        with pytest.raises(Exception, match="Repository directory missing"):
            sandbox.create(SandboxConfig(image="testq-sandbox-node:latest"), tmp_path / "missing")
        assert not sandbox.owned
        assert not sandbox.client.containers.list(all=True, filters={"label": f"testq.run_id={sandbox.run_id}"})
    finally:
        sandbox.cleanup()
