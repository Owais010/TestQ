"""Real Docker tests for Phase 3 Deterministic Test Engine, gated by TESTQ_DOCKER_TESTS=1."""
import asyncio
import hashlib
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.discovery import DiscoverySession, Evidence
from app.models.test_case import TestCase, TestResult
from app.models.test_run import TestRunStatus as S
from app.schemas.common import ExecutionResult
from app.schemas.test_case import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    TestResultStatus,
)
from app.services.baseline_generator import BaselineGenerator
from app.services.sandbox_manager import SandboxManager
from app.worker.pipeline import Pipeline
from app.worker.control import RunControl
from tests.test_docker_hardening import git_fixture, LocalGit
from tests.test_hardening import new_run
from testq_browser.schemas import ApplicationMap

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("TESTQ_DOCKER_TESTS") != "1", reason="Requires real Docker"
    ),
]


async def test_real_deterministic_testing_pipeline(db, tmp_path, monkeypatch):
    """End-to-end integration test with real Docker sandbox container:
    clone -> build -> start -> discovery -> baseline generation -> test execution -> persistence -> cleanup.
    Proves execution of HOME, NAV, UI (click, fill, select, check, uncheck), and API categories.
    """
    source = git_fixture(tmp_path, "success")
    (source / "server.js").write_text(r"""
const http = require('http');
const port = process.env.PORT || 4321;
const html = `<!doctype html><title>TestQ Deterministic Fixture</title>
<h1>Phase 3 Test Engine Fixture</h1>
<a href="/about">About Us</a>
<form id="contact-form" action="/api/contact" method="post">
  <input data-testid="username" name="username" type="text" value="original_user">
  <input data-testid="subscribe" name="subscribe" type="checkbox">
  <select data-testid="plan" name="plan">
    <option value="basic">Basic</option>
    <option value="pro">Pro</option>
  </select>
  <button id="click-btn" data-testid="click-btn" type="button" onclick="document.getElementById('heading').innerText='Clicked!';">Click Me</button>
  <button type="submit" id="submit-btn" data-testid="submit-btn">Submit</button>
</form>
<h2 id="heading">Original Heading</h2>
<script>
  console.log('App loaded successfully');
  fetch('/api/health').then(r => r.json());
</script>`;

http.createServer((req, res) => {
  if (req.url === '/api/contact' && req.method === 'POST') {
    res.setHeader('Content-Type', 'application/json');
    return res.end(JSON.stringify({ status: 'received' }));
  }
  if (req.url === '/api/health') {
    res.setHeader('Content-Type', 'application/json');
    return res.end(JSON.stringify({ status: 'ok', version: '1.0' }));
  }
  if (req.url === '/about') {
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><title>About</title><h1>About Page</h1>');
  }
  res.setHeader('Content-Type', 'text/html');
  res.end(html);
}).listen(port, '127.0.0.1');
""")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(source),
            "-c", "user.name=TestQ",
            "-c", "user.email=testq@example.invalid",
            "commit", "-m", "Phase 3 comprehensive test fixture",
        ],
        check=True,
        capture_output=True,
    )

    evidence_root = Path(os.environ.get("TESTQ_FIXTURE_EVIDENCE_DIR", str(tmp_path / "evidence"))).resolve()
    monkeypatch.setattr(settings, "evidence_dir", evidence_root)

    run = await new_run(db)
    run.discovery_enabled = True
    run.testing_enabled = True
    await db.commit()

    pipeline = Pipeline(db, RunControl(240), github=LocalGit(tmp_path / "clones", source))
    await pipeline.run(run)

    # 1. State machine outcome must be COMPLETED
    assert run.status == S.COMPLETED, f"Run failed with reason: {run.failure_reason}"
    assert run.progress.get("testing") == "completed"
    assert run.progress.get("discovering") == "completed"

    # 2. Verify discovery session and application map
    session = (await db.execute(select(DiscoverySession).where(DiscoverySession.run_id == run.id))).scalar_one()
    app_map = ApplicationMap.model_validate(session.application_map)
    assert len(app_map.pages) >= 2  # / and /about
    assert len(app_map.api_endpoints) >= 1  # /api/health

    # 3. Verify generated TestCase models in DB
    cases = (await db.execute(select(TestCase).where(TestCase.run_id == run.id))).scalars().all()
    assert len(cases) >= 4
    case_ids = {c.definition.get("id") for c in cases}
    assert "HOME-001" in case_ids
    assert "NAV-001" in case_ids
    assert "UI-ACT-001" in case_ids
    assert "API-001" in case_ids

    # 4. Verify executed TestResult models in DB for all major categories
    results = (await db.execute(select(TestResult).where(TestResult.run_id == run.id))).scalars().all()
    assert len(results) == len(cases)
    assert run.total_tests == len(results)
    assert run.passed_tests >= 4

    case_map = {c.id: c.definition.get("id") for c in cases}
    results_by_test_id = {case_map[r.test_case_id]: r for r in results}

    # Verify exact persisted result: HOME-001 -> PASS
    assert "HOME-001" in results_by_test_id
    home_result = results_by_test_id["HOME-001"]
    assert home_result.status == TestResultStatus.PASS
    assert any(a.get("assertion") == "page_loaded" and a.get("passed") for a in home_result.assertions_json)
    assert any(a.get("assertion") == "http_status" and a.get("passed") for a in home_result.assertions_json)

    # Verify exact persisted result: NAV-001 -> PASS
    assert "NAV-001" in results_by_test_id
    nav_result = results_by_test_id["NAV-001"]
    assert nav_result.status == TestResultStatus.PASS
    assert any(a.get("assertion") == "url_matches" and a.get("passed") for a in nav_result.assertions_json)

    # Verify exact persisted result: UI-ACT-001 -> PASS with real actions
    assert "UI-ACT-001" in results_by_test_id
    ui_result = results_by_test_id["UI-ACT-001"]
    assert ui_result.status == TestResultStatus.PASS
    assert len(ui_result.steps_json) >= 1
    ui_actions = [s.get("action") for s in ui_result.steps_json]
    assert "goto" in ui_actions
    assert "fill" in ui_actions
    assert "check" in ui_actions
    assert "uncheck" in ui_actions
    assert "select" in ui_actions
    assert "click" in ui_actions

    # Verify exact persisted result: API-001 -> PASS with real assertions
    assert "API-001" in results_by_test_id
    api_result = results_by_test_id["API-001"]
    assert api_result.status == TestResultStatus.PASS
    api_ast_names = {a.get("assertion") for a in api_result.assertions_json if a.get("passed")}
    assert "status_code" in api_ast_names
    assert "content_type" in api_ast_names
    assert "json_field_present" in api_ast_names
    assert "json_value" in api_ast_names

    # 5. Verify test evidence with test_result_id linkage
    test_evidence = (
        await db.execute(
            select(Evidence).where(Evidence.run_id == run.id, Evidence.test_result_id.is_not(None))
        )
    ).scalars().all()
    assert len(test_evidence) >= 1

    # Check evidence file existence and hash verification
    for ev in test_evidence:
        assert ev.test_result_id in [r.id for r in results]
        ev_path = evidence_root / ev.path
        assert ev_path.is_file(), f"Evidence file missing on disk: {ev_path}"
        assert ev.size_bytes == ev_path.stat().st_size
        assert hashlib.sha256(ev_path.read_bytes()).hexdigest() == ev.sha256

    # Verify discovery evidence also exists independently
    discovery_evidence = (
        await db.execute(
            select(Evidence).where(Evidence.run_id == run.id, Evidence.test_result_id.is_(None))
        )
    ).scalars().all()
    assert len(discovery_evidence) >= 1

    # 6. Verify sandbox cleanup: no containers leaked
    assert not pipeline.sandbox.client.containers.list(
        all=True, filters={"label": f"testq.run_id={run.id}"}
    )


async def test_real_deterministic_testing_active_cancellation(db, tmp_path, monkeypatch):
    """Test that cancellation while a test is actively executing terminates the container and marks CANCELLED."""
    source = git_fixture(tmp_path, "success")
    (source / "server.js").write_text(r"""
const http = require('http');
http.createServer((req, res) => {
  if (req.url === '/slow-cancel-route') {
    // Controlled slow fixture: keep connection open for 15s so the test is actively executing
    setTimeout(() => {
      res.setHeader('Content-Type', 'text/html');
      res.end('<h1>Slow route complete</h1>');
    }, 15000);
    return;
  }
  res.setHeader('Content-Type', 'text/html');
  res.end('<!doctype html><title>Cancel Test</title><h1>Cancel Test Home</h1>');
}).listen(process.env.PORT || 4321, '127.0.0.1');
""")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=TestQ", "-c", "user.email=testq@example.invalid", "commit", "-m", "cancel test"],
        check=True, capture_output=True
    )

    control = RunControl(240)
    run = await new_run(db)
    run.discovery_enabled = True
    run.testing_enabled = True
    await db.commit()

    pipeline = Pipeline(db, control, github=LocalGit(tmp_path / "clones", source))

    # Controlled slow test definition to ensure the in-sandbox test runner is actively executing
    original_generate = BaselineGenerator.generate_suite

    def generate_slow_suite(app_map, run_id):
        suite = original_generate(app_map, run_id)
        slow_test = UITestDefinition(
            id="SLOW-001",
            type="ui",
            title="Slow active test for cancellation",
            priority="high",
            steps=[
                UITestStep(action="goto", target="/slow-cancel-route", timeout_ms=15000),
            ],
            expected=[UIAssertion(assertion="page_loaded")],
        )
        suite.insert(
            0,
            TestCase(
                run_id=run_id,
                type="ui",
                title=slow_test.title,
                priority=slow_test.priority,
                definition=slow_test.model_dump(mode="json"),
            ),
        )
        return suite

    monkeypatch.setattr(BaselineGenerator, "generate_suite", generate_slow_suite)

    active_test_evidence = {}
    original_execute = SandboxManager.execute

    def synchronized_execute(self, container_id, command, **kwargs):
        if "testq_browser.test_runner" in command:
            # 1. Launch in-sandbox test runner process
            user = kwargs.get("user", "10002:10002")
            working_dir = kwargs.get("working_dir")
            source_lbl = kwargs.get("source", "command")
            environment = kwargs.get("environment")

            exec_id, stdout, stderr = self._launch(
                container_id, command, working_dir, source_lbl, environment, user=user
            )

            # 2. Synchronize: Wait until Docker confirms the process has ACTUALLY started and is running
            running_state = None
            for _ in range(50):
                inspect_info = self.client.api.exec_inspect(exec_id)
                if inspect_info.get("Running"):
                    running_state = inspect_info
                    break
                time.sleep(0.1)

            assert running_state is not None, "In-sandbox test runner failed to start"
            assert running_state.get("Running") is True, "In-sandbox test process is not running"
            assert running_state.get("Pid", 0) > 0, "In-sandbox test process has invalid PID"

            # Query container process table as host-level evidence that the process is alive in the container
            container = self.client.containers.get(container_id)
            top_info = container.top()

            active_test_evidence["exec_id"] = exec_id
            active_test_evidence["pid"] = running_state["Pid"]
            active_test_evidence["running"] = True
            active_test_evidence["cmd"] = command
            active_test_evidence["top_processes"] = top_info.get("Processes", [])

            # 3. Request cancellation WHILE IT IS ACTIVELY RUNNING
            control.cancel()

            # 4. Resume the normal execution wait loop, which will immediately check control
            # and trigger container kill + raise RunCancelled
            begin = time.monotonic()
            timeout = kwargs.get("timeout") or settings.docker_timeout
            timed_out = False
            code = None
            try:
                while True:
                    self.check()
                    if time.monotonic() - begin >= timeout:
                        self.kill(container_id)
                        timed_out = True
                        code = 124
                        break
                    state = self.client.api.exec_inspect(exec_id)
                    if not state["Running"]:
                        code = state["ExitCode"]
                        break
                    time.sleep(0.1)
            except BaseException:
                self.kill(container_id)
                raise

            return ExecutionResult(
                command=command, exit_code=code if code is not None else -1,
                stdout=self.read_file(container_id, stdout),
                stderr=self.read_file(container_id, stderr),
                started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                duration_seconds=time.monotonic() - begin, timed_out=timed_out,
            )

        return original_execute(self, container_id, command, **kwargs)

    monkeypatch.setattr(SandboxManager, "execute", synchronized_execute)
    await pipeline.run(run)

    # 1. Verify that the in-sandbox test runner process was actively running when cancellation was requested
    assert active_test_evidence.get("running") is True
    assert active_test_evidence.get("pid", 0) > 0
    assert any(
        "test_runner" in " ".join(proc) for proc in active_test_evidence.get("top_processes", [])
    ), f"Expected test_runner in container top processes: {active_test_evidence.get('top_processes')}"

    # 2. Verify that execution stopped and result/state became CANCELLED
    assert run.status == S.CANCELLED
    results = (await db.execute(select(TestResult).where(TestResult.run_id == run.id))).scalars().all()
    assert len(results) >= 1
    assert any(r.status == TestResultStatus.CANCELLED for r in results)

    # 3. Verify complete cleanup: no orphaned container or workspace
    assert not pipeline.sandbox.client.containers.list(
        all=True, filters={"label": f"testq.run_id={run.id}"}
    )
    assert not (tmp_path / "clones" / run.id).exists()


async def test_real_deterministic_testing_timeout(db, tmp_path, monkeypatch):
    """Test that a test exceeding its timeout records TIMEOUT and terminates cleanly without leaking."""
    source = git_fixture(tmp_path, "success")
    (source / "server.js").write_text(r"""
const http = require('http');
http.createServer((req, res) => {
  if (req.url === '/slow-hang') {
    // Deliberately delay response longer than timeout
    setTimeout(() => {
      res.setHeader('Content-Type', 'text/html');
      res.end('<h1>Eventually Loaded</h1>');
    }, 10000);
    return;
  }
  res.setHeader('Content-Type', 'text/html');
  res.end('<h1>Timeout Test</h1>');
}).listen(process.env.PORT || 4321, '127.0.0.1');
""")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=TestQ", "-c", "user.email=testq@example.invalid", "commit", "-m", "timeout test"],
        check=True, capture_output=True
    )

    run = await new_run(db)
    run.discovery_enabled = True
    run.testing_enabled = True
    await db.commit()

    pipeline = Pipeline(db, RunControl(240), github=LocalGit(tmp_path / "clones", source))

    # Inject a test definition that navigates to slow endpoint with a short 1s timeout
    original_generate = BaselineGenerator.generate_suite

    def generate_suite_with_timeout(app_map, run_id):
        suite = original_generate(app_map, run_id)
        timeout_def = UITestDefinition(
            id="TIMEOUT-001",
            type="ui",
            title="Deliberate timeout test",
            priority="high",
            steps=[
                UITestStep(
                    action="goto",
                    target="/slow-hang",
                    timeout_ms=1000,
                ),
            ],
            expected=[UIAssertion(assertion="page_loaded")],
        )
        suite.append(
            TestCase(
                run_id=run_id,
                type="ui",
                title=timeout_def.title,
                priority=timeout_def.priority,
                definition=timeout_def.model_dump(mode="json"),
            )
        )
        return suite

    monkeypatch.setattr(BaselineGenerator, "generate_suite", generate_suite_with_timeout)
    await pipeline.run(run)

    assert run.status == S.COMPLETED

    # Check that TIMEOUT-001 produced a TIMEOUT result
    timeout_result = (
        await db.execute(
            select(TestResult)
            .join(TestCase, TestResult.test_case_id == TestCase.id)
            .where(TestCase.run_id == run.id, TestCase.title == "Deliberate timeout test")
        )
    ).scalar_one()

    assert timeout_result.status == TestResultStatus.TIMEOUT
    assert "timed out" in (timeout_result.error or "").lower()

    # Verify no container was leaked
    assert not pipeline.sandbox.client.containers.list(
        all=True, filters={"label": f"testq.run_id={run.id}"}
    )
