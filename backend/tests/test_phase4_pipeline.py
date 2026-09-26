"""Tests for Phase 4 pipeline integration: AI test planning, generation, fallback, and persistence."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.test_case import TestCase, TestResult
from app.schemas.test_case import TestResultStatus
from app.ai.base import AIProvider, AIUnavailableError
from app.worker.pipeline import Pipeline
from testq_browser.schemas import ApplicationMap, PageRecord, DiscoveryLimits, APIEndpoint


@pytest.fixture
def mock_sandbox():
    sandbox = MagicMock()
    sandbox.image_exists.return_value = True
    sandbox.browser_available.return_value = True
    sandbox.create.return_value = {"container_id": "mock-cont-p4"}
    sandbox.restrict_network.return_value = None
    sandbox.kill.return_value = None
    sandbox.collect_logs.return_value = []
    sandbox.cleanup.return_value = None
    return sandbox


@pytest.mark.asyncio
async def test_pipeline_ai_generation_and_execution_flow(db: AsyncSession, mock_sandbox, tmp_path):
    """Test full Phase 4 pipeline with mocked AI provider:
    Discovery -> Baseline Gen -> AI Planning -> AI Gen -> Combined Execution -> Persistence with source.
    """
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

    mock_app_map = ApplicationMap(
        run_id=run.id,
        session_id="sess-p4",
        base_url="http://127.0.0.1:3000",
        pages=[PageRecord(url="http://127.0.0.1:3000/", depth=0, title="Home")],
        api_endpoints=[APIEndpoint(method="GET", path="/api/health", statuses=[200])],
        limits=DiscoveryLimits(),
    )

    mock_cfg = MagicMock(
        language="node", framework="express", package_manager="npm",
        expected_port=3000, model_dump=lambda: {},
        install_command="npm install", start_command="npm start",
    )

    mock_ai = AsyncMock(spec=AIProvider)
    # 1. AI Planning returns a strategy
    # 2. AI Generator returns a test case
    mock_ai.generate.side_effect = [
        # Call 1: TestPlanner
        {
            "summary": "AI test strategy",
            "items": [
                {
                    "id": "STRAT-001",
                    "category": "api",
                    "target": "/api/health",
                    "description": "Test health check status",
                    "risk_level": "medium",
                    "priority": "high",
                }
            ],
        },
        # Call 2: TestGenerator
        {
            "ui_tests": [
                {
                    "id": "AI-RAW-001",
                    "type": "ui",
                    "title": "AI explored home page test",
                    "priority": "medium",
                    "steps": [
                        {"action": "goto", "target": "/"},
                        {"action": "wait", "timeout_ms": 200},
                    ],
                    "expected": [{"assertion": "page_loaded"}],
                }
            ],
            "api_tests": [],
        },
    ]

    pipeline = Pipeline(
        db,
        sandbox_factory=lambda *a, **kw: mock_sandbox,
        ai_provider=mock_ai,
    )

    with patch("app.worker.pipeline.detect_project", return_value=mock_cfg), \
         patch("app.services.build_manager.BuildManager.install_dependencies"), \
         patch("app.services.build_manager.BuildManager.build_project"), \
         patch("app.services.build_manager.BuildManager.start_application", return_value="exec-1"), \
         patch("app.services.health_checker.HealthChecker.check_sandbox") as mock_health, \
         patch("app.services.github_service.GitHubService.clone_repository", return_value={"commit_sha": "abc", "branch": "main"}), \
         patch("app.services.github_service.GitHubService.cleanup_workspace"), \
         patch("app.services.discovery_service.DiscoveryService.discover", new=AsyncMock(return_value=mock_app_map)), \
         patch("app.services.test_executor.TestExecutor.execute_suite") as mock_exec_suite:

        mock_health.return_value = MagicMock(is_healthy=True, url="http://127.0.0.1:3000", status_code=200)

        # Mock execute_suite to return PASS for all executed test cases
        async def fake_execute_suite(base_url, run_id, session_id, test_cases):
            return [
                TestResult(id=f"tr-{tc.id}", run_id=run_id, test_case_id=tc.id, status=TestResultStatus.PASS)
                for tc in test_cases
            ]
        mock_exec_suite.side_effect = fake_execute_suite

        await pipeline.run(run)

    await db.refresh(run)
    assert run.status == S.COMPLETED

    # Verify persisted TestCase records
    persisted_cases = (
        await db.execute(select(TestCase).where(TestCase.run_id == run.id))
    ).scalars().all()

    sources = {tc.source for tc in persisted_cases}
    assert "baseline" in sources
    assert "ai" in sources

    # At least one baseline and one AI test
    baseline_cases = [tc for tc in persisted_cases if tc.source == "baseline"]
    ai_cases = [tc for tc in persisted_cases if tc.source == "ai"]
    assert len(baseline_cases) >= 1
    assert len(ai_cases) >= 1

    ai_case = ai_cases[0]
    assert ai_case.definition["id"].startswith("AI-")
    assert ai_case.title == "AI explored home page test"

    # Verify API lists both baseline and AI sources
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/test-runs/{run.id}/test-cases")
            assert resp.status_code == 200
            data = resp.json()
            test_cases = data["test_cases"]
            assert any(tc["source"] == "baseline" for tc in test_cases)
            assert any(tc["source"] == "ai" for tc in test_cases)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pipeline_ai_unavailable_fallback_to_baseline(db: AsyncSession, mock_sandbox):
    """When Ollama is unavailable, the pipeline must NOT fail or classify it as an application bug.
    It should log a warning, fall back to executing baseline tests, and finish COMPLETED.
    """
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

    mock_app_map = ApplicationMap(
        run_id=run.id,
        session_id="sess-fallback",
        base_url="http://127.0.0.1:3000",
        pages=[PageRecord(url="http://127.0.0.1:3000/", depth=0, title="Home")],
        limits=DiscoveryLimits(),
    )

    mock_cfg = MagicMock(
        language="node", framework="express", package_manager="npm",
        expected_port=3000, model_dump=lambda: {},
        install_command="npm install", start_command="npm start",
    )

    mock_ai = AsyncMock(spec=AIProvider)
    mock_ai.generate.side_effect = AIUnavailableError("Local Ollama is offline")

    pipeline = Pipeline(
        db,
        sandbox_factory=lambda *a, **kw: mock_sandbox,
        ai_provider=mock_ai,
    )

    with patch("app.worker.pipeline.detect_project", return_value=mock_cfg), \
         patch("app.services.build_manager.BuildManager.install_dependencies"), \
         patch("app.services.build_manager.BuildManager.build_project"), \
         patch("app.services.build_manager.BuildManager.start_application", return_value="exec-1"), \
         patch("app.services.health_checker.HealthChecker.check_sandbox") as mock_health, \
         patch("app.services.github_service.GitHubService.clone_repository", return_value={"commit_sha": "abc", "branch": "main"}), \
         patch("app.services.github_service.GitHubService.cleanup_workspace"), \
         patch("app.services.discovery_service.DiscoveryService.discover", new=AsyncMock(return_value=mock_app_map)), \
         patch("app.services.test_executor.TestExecutor.execute_suite") as mock_exec_suite:

        mock_health.return_value = MagicMock(is_healthy=True, url="http://127.0.0.1:3000", status_code=200)

        async def fake_execute_suite(base_url, run_id, session_id, test_cases):
            return [
                TestResult(id=f"tr-{tc.id}", run_id=run_id, test_case_id=tc.id, status=TestResultStatus.PASS)
                for tc in test_cases
            ]
        mock_exec_suite.side_effect = fake_execute_suite

        await pipeline.run(run)

    await db.refresh(run)
    # The run must NOT fail because Ollama is down!
    assert run.status == S.COMPLETED

    persisted_cases = (
        await db.execute(select(TestCase).where(TestCase.run_id == run.id))
    ).scalars().all()

    # Baseline tests ran and were persisted
    assert len(persisted_cases) >= 1
    assert all(tc.source == "baseline" for tc in persisted_cases)
