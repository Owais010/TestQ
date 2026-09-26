"""Tests for Phase 3 pipeline state machine, execution, and evidence integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.discovery import DiscoverySession, Evidence
from app.models.test_case import TestCase, TestResult
from app.schemas.test_case import UITestDefinition, UITestStep, UIAssertion, TestResultStatus
from app.services.evidence_manager import EvidenceManager
from app.worker.pipeline import Pipeline, InvalidTransition
from app.worker.control import RunControl
from testq_browser.schemas import ApplicationMap, PageRecord, DiscoveryLimits


@pytest.fixture
def mock_sandbox():
    sandbox = MagicMock()
    sandbox.image_exists.return_value = True
    sandbox.browser_available.return_value = True
    sandbox.create.return_value = {"container_id": "mock-cont-123"}
    sandbox.restrict_network.return_value = None
    sandbox.kill.return_value = None
    sandbox.collect_logs.return_value = []
    sandbox.cleanup.return_value = None
    return sandbox


@pytest.mark.asyncio
async def test_pipeline_testing_requires_discovery(db: AsyncSession, mock_sandbox):
    project = Project(repository_url="https://github.com/example/repo", default_branch="main")
    db.add(project)
    await db.flush()

    run = TestRun(
        project_id=project.id,
        branch="main",
        status=S.QUEUED,
        discovery_enabled=False,
        testing_enabled=True,
    )
    db.add(run)
    await db.commit()

    pipeline = Pipeline(db, sandbox_factory=lambda *a, **kw: mock_sandbox)

    await pipeline.run(run)

    await db.refresh(run)
    assert run.status == S.FAILED
    assert "Testing requires discovery to be enabled" in (run.failure_reason or "")


@pytest.mark.asyncio
async def test_pipeline_testing_enabled_flow(db: AsyncSession, mock_sandbox, tmp_path):
    project = Project(repository_url="https://github.com/example/repo", default_branch="main")
    db.add(project)
    await db.flush()

    run = TestRun(
        project_id=project.id,
        branch="main",
        status=S.QUEUED,
        discovery_enabled=True,
        testing_enabled=True,
    )
    db.add(run)
    await db.commit()

    pipeline = Pipeline(db, sandbox_factory=lambda *a, **kw: mock_sandbox)

    mock_app_map = ApplicationMap(
        run_id=run.id,
        session_id="sess-phase3",
        base_url="http://127.0.0.1:3000",
        pages=[PageRecord(url="http://127.0.0.1:3000/", depth=0)],
        limits=DiscoveryLimits(),
    )

    mock_cfg = MagicMock(language="node", framework="express", package_manager="npm", expected_port=3000, model_dump=lambda: {})

    with patch("app.worker.pipeline.detect_project", return_value=mock_cfg), \
         patch("app.services.build_manager.BuildManager.install_dependencies"), \
         patch("app.services.build_manager.BuildManager.build_project"), \
         patch("app.services.build_manager.BuildManager.start_application", return_value="exec-1"), \
         patch("app.services.health_checker.HealthChecker.check_sandbox") as mock_health, \
         patch("app.services.github_service.GitHubService.clone_repository", return_value={"commit_sha": "abc", "branch": "main"}), \
         patch("app.services.github_service.GitHubService.cleanup_workspace"), \
         patch("app.services.discovery_service.DiscoveryService.discover", new=AsyncMock(return_value=mock_app_map)), \
         patch("app.services.test_executor.TestExecutor.execute_suite", new=AsyncMock(return_value=[
             TestResult(id="tr-1", run_id=run.id, test_case_id="tc-1", status=TestResultStatus.PASS)
         ])):

        mock_health.return_value = MagicMock(is_healthy=True, url="http://127.0.0.1:3000", status_code=200)

        # Pre-create discovery session so session_id lookup succeeds
        sess = DiscoverySession(id="sess-phase3", run_id=run.id, application_map=mock_app_map.model_dump(mode="json"))
        db.add(sess)
        await db.commit()

        await pipeline.run(run)

    await db.refresh(run)
    # Verification: testing-enabled run finishes in COMPLETED state!
    assert run.status == S.COMPLETED
    assert run.progress.get("testing") == "completed"
    assert run.progress.get("discovering") == "completed"


@pytest.mark.asyncio
async def test_evidence_storage_and_api(db: AsyncSession, tmp_path):
    project = Project(repository_url="https://github.com/example/repo", default_branch="main")
    db.add(project)
    await db.flush()

    run = TestRun(
        project_id=project.id,
        branch="main",
        status=S.COMPLETED,
        discovery_enabled=True,
        testing_enabled=True,
    )
    db.add(run)
    await db.flush()

    sess = DiscoverySession(
        id="sess-ev-1",
        run_id=run.id,
        application_map={"run_id": run.id, "session_id": "sess-ev-1", "base_url": "http://127.0.0.1:3000", "pages": []},
    )
    db.add(sess)
    await db.flush()

    tc = TestCase(
        run_id=run.id,
        type="ui",
        title="Sample Test",
        definition={"type": "ui", "id": "HOME-001", "title": "Sample", "steps": [{"action": "goto", "target": "/"}], "expected": [{"assertion": "page_loaded"}]},
    )
    db.add(tc)
    await db.flush()

    tr = TestResult(
        run_id=run.id,
        test_case_id=tc.id,
        status="PASS",
    )
    db.add(tr)
    await db.commit()

    # Store test evidence via EvidenceManager
    ev_mgr = EvidenceManager(db=db, root=tmp_path)
    ev_row = await ev_mgr.store_test_json(
        run_id=run.id,
        session_id=sess.id,
        test_result_id=tr.id,
        filename=f"result_{tc.id}.json",
        kind="test_result",
        payload={"test_id": tc.id, "status": "PASS"},
    )
    assert ev_row.test_result_id == tr.id

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch("app.api.discovery.settings.evidence_dir", str(tmp_path)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/test-runs/{run.id}/evidence")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["evidence"]) >= 1
                item = next(e for e in data["evidence"] if e["id"] == ev_row.id)
                assert item["test_result_id"] == tr.id
                assert item["kind"] == "test_result"

                # Test download
                dl_resp = await client.get(item["url"])
                assert dl_resp.status_code == 200
                content = dl_resp.json()
                assert content["status"] == "PASS"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_test_cases_and_results_api(db: AsyncSession):
    project = Project(repository_url="https://github.com/example/repo", default_branch="main")
    db.add(project)
    await db.flush()

    run = TestRun(
        project_id=project.id,
        branch="main",
        status=S.COMPLETED,
        discovery_enabled=True,
        testing_enabled=True,
    )
    db.add(run)
    await db.flush()

    tc = TestCase(
        run_id=run.id,
        type="ui",
        title="Homepage Check",
        definition={"type": "ui", "id": "HOME-001", "title": "Homepage Check", "steps": [{"action": "goto", "target": "/"}], "expected": [{"assertion": "page_loaded"}]},
    )
    db.add(tc)
    await db.flush()

    tr = TestResult(
        run_id=run.id,
        test_case_id=tc.id,
        status="PASS",
        duration_ms=120.0,
    )
    db.add(tr)
    await db.commit()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. List test cases
            res = await client.get(f"/api/test-runs/{run.id}/test-cases")
            assert res.status_code == 200
            assert res.json()["total"] == 1
            assert res.json()["test_cases"][0]["title"] == "Homepage Check"

            # 2. Get specific test case
            res_single = await client.get(f"/api/test-runs/{run.id}/test-cases/{tc.id}")
            assert res_single.status_code == 200
            assert res_single.json()["id"] == tc.id

            # 3. List test results
            res_results = await client.get(f"/api/test-runs/{run.id}/test-results")
            assert res_results.status_code == 200
            assert res_results.json()["total"] == 1
            assert res_results.json()["passed"] == 1
            assert res_results.json()["test_results"][0]["status"] == "PASS"

            # 4. Get specific test result
            res_tr = await client.get(f"/api/test-runs/{run.id}/test-results/{tr.id}")
            assert res_tr.status_code == 200
            assert res_tr.json()["id"] == tr.id
    finally:
        app.dependency_overrides.clear()
