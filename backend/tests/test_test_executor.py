"""Tests for TestExecutor dispatcher, limits, and persistence."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.test_case import TestCase, TestResult
from app.schemas.test_case import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    APITestDefinition,
    APIRequestSpec,
    APIAssertion,
    TestExecutionResult,
    TestResultStatus,
)
from app.services.test_executor import TestExecutor
from app.worker.control import RunControl


@pytest.fixture
async def sample_run(db: AsyncSession):
    project = Project(repository_url="https://github.com/example/repo", default_branch="main")
    db.add(project)
    await db.flush()

    run = TestRun(
        project_id=project.id,
        branch="main",
        status=S.TESTING,
        discovery_enabled=True,
        testing_enabled=True,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_execute_ui_and_api_tests(db: AsyncSession, sample_run: TestRun):
    control = RunControl(600)
    sandbox = MagicMock()
    executor = TestExecutor(
        db=db,
        sandbox=sandbox,
        container_id="cont-123",
        control=control,
        blocking=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    # Mock PlaywrightRunner and APITester
    ui_exec_res = TestExecutionResult(
        test_id="HOME-001",
        run_id=sample_run.id,
        status=TestResultStatus.PASS,
        started_at="2026-09-25T12:00:00Z",
        finished_at="2026-09-25T12:00:01Z",
        duration_ms=1050.0,
    )
    executor.playwright_runner.execute_test = AsyncMock(return_value=ui_exec_res)

    api_exec_res = TestExecutionResult(
        test_id="API-001",
        run_id=sample_run.id,
        status=TestResultStatus.PASS,
        started_at="2026-09-25T12:00:01Z",
        finished_at="2026-09-25T12:00:02Z",
        duration_ms=45.0,
    )
    executor.api_tester.execute_test = AsyncMock(return_value=api_exec_res)

    tc1 = TestCase(
        run_id=sample_run.id,
        type="ui",
        title="Homepage loads",
        priority="critical",
        definition=UITestDefinition(
            id="HOME-001",
            title="Homepage loads",
            steps=[UITestStep(action="goto", target="/")],
            expected=[UIAssertion(assertion="page_loaded")],
        ).model_dump(mode="json"),
    )
    tc2 = TestCase(
        run_id=sample_run.id,
        type="api",
        title="Health endpoint",
        priority="high",
        definition=APITestDefinition(
            id="API-001",
            title="Health endpoint",
            request=APIRequestSpec(method="GET", path="/health"),
            expected=[APIAssertion(assertion="status_code", expected=200)],
        ).model_dump(mode="json"),
    )
    db.add_all([tc1, tc2])
    await db.commit()

    results = await executor.execute_suite(
        base_url="http://127.0.0.1:3000",
        run_id=sample_run.id,
        session_id="sess-abc",
        test_cases=[tc1, tc2],
    )

    assert len(results) == 2
    assert results[0].status == TestResultStatus.PASS
    assert results[1].status == TestResultStatus.PASS

    # Verify counts in test_run
    await db.refresh(sample_run)
    assert sample_run.total_tests == 2
    assert sample_run.passed_tests == 2
    assert sample_run.failed_tests == 0


@pytest.mark.asyncio
async def test_step_limit_enforcement(db: AsyncSession, sample_run: TestRun):
    control = RunControl(600)
    sandbox = MagicMock()
    executor = TestExecutor(
        db=db,
        sandbox=sandbox,
        container_id="cont-123",
        control=control,
        blocking=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    # 10 steps with limit of 5
    steps = [UITestStep(action="goto", target="/")] + [
        UITestStep(action="wait", timeout_ms=100) for _ in range(9)
    ]
    tc = TestCase(
        run_id=sample_run.id,
        type="ui",
        title="Too many steps",
        priority="low",
        definition=UITestDefinition(
            id="STEPS-001",
            title="Too many steps",
            steps=steps,
            expected=[UIAssertion(assertion="page_loaded")],
        ).model_dump(mode="json"),
    )
    db.add(tc)
    await db.commit()

    result = await executor.execute_test(
        base_url="http://127.0.0.1:3000",
        run_id=sample_run.id,
        session_id="sess-abc",
        test_case=tc,
        limits={"max_steps_per_test": 5},
    )

    assert result.status == TestResultStatus.ERROR
    assert "exceeds maximum allowed" in (result.error or "")


@pytest.mark.asyncio
async def test_cancellation_during_suite(db: AsyncSession, sample_run: TestRun):
    control = RunControl(600)
    sandbox = MagicMock()
    executor = TestExecutor(
        db=db,
        sandbox=sandbox,
        container_id="cont-123",
        control=control,
        blocking=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    # Cancel control upfront
    control.cancel()

    tc = TestCase(
        run_id=sample_run.id,
        type="ui",
        title="Will be cancelled",
        priority="low",
        definition=UITestDefinition(
            id="CANCEL-001",
            title="Will be cancelled",
            steps=[UITestStep(action="goto", target="/")],
            expected=[UIAssertion(assertion="page_loaded")],
        ).model_dump(mode="json"),
    )
    db.add(tc)
    await db.commit()

    results = await executor.execute_suite(
        base_url="http://127.0.0.1:3000",
        run_id=sample_run.id,
        session_id="sess-abc",
        test_cases=[tc],
    )

    assert len(results) == 1
    assert results[0].status == TestResultStatus.CANCELLED


@pytest.mark.asyncio
async def test_max_tests_per_run_truncation(db: AsyncSession, sample_run: TestRun):
    """Verify that execute_suite deterministically truncates test suites exceeding MAX_TESTS_PER_RUN (50)."""
    control = RunControl(600)
    sandbox = MagicMock()
    executor = TestExecutor(
        db=db,
        sandbox=sandbox,
        container_id="cont-123",
        control=control,
        blocking=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    # Mock execute_test to quickly return PASS
    async def mock_exec_test(base_url, run_id, session_id, test_case, limits=None):
        res = TestResult(
            run_id=run_id,
            test_case_id=test_case.id,
            status=TestResultStatus.PASS,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=10.0,
        )
        db.add(res)
        await db.commit()
        return res

    from datetime import datetime, timezone
    executor.execute_test = mock_exec_test

    # Generate 60 test cases
    cases = []
    for i in range(60):
        tc = TestCase(
            run_id=sample_run.id,
            type="ui",
            title=f"Test {i}",
            priority="medium",
            definition=UITestDefinition(
                id=f"TEST-{i:03d}",
                title=f"Test {i}",
                steps=[UITestStep(action="goto", target="/")],
                expected=[UIAssertion(assertion="page_loaded")],
            ).model_dump(mode="json"),
        )
        cases.append(tc)
    db.add_all(cases)
    await db.commit()

    # 1. Default limit (50)
    results = await executor.execute_suite(
        base_url="http://127.0.0.1:3000",
        run_id=sample_run.id,
        session_id="sess-abc",
        test_cases=cases,
    )
    assert len(results) == 50
    await db.refresh(sample_run)
    assert sample_run.total_tests == 50

    # 2. Explicit custom limit (5)
    results_custom = await executor.execute_suite(
        base_url="http://127.0.0.1:3000",
        run_id=sample_run.id,
        session_id="sess-abc",
        test_cases=cases,
        limits={"max_tests_per_run": 5},
    )
    assert len(results_custom) == 5


@pytest.mark.asyncio
async def test_action_timeout_result_status(db: AsyncSession, sample_run: TestRun):
    """Verify that an action timeout reports TestResultStatus.TIMEOUT and records error."""
    control = RunControl(600)
    sandbox = MagicMock()
    executor = TestExecutor(
        db=db,
        sandbox=sandbox,
        container_id="cont-123",
        control=control,
        blocking=lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    timeout_exec_res = TestExecutionResult(
        test_id="TIMEOUT-001",
        run_id=sample_run.id,
        status=TestResultStatus.TIMEOUT,
        started_at="2026-09-25T12:00:00Z",
        finished_at="2026-09-25T12:00:05Z",
        duration_ms=5000.0,
        error="Step timed out: Timeout 5000ms exceeded waiting for locator",
    )
    executor.playwright_runner.execute_test = AsyncMock(return_value=timeout_exec_res)

    tc = TestCase(
        run_id=sample_run.id,
        type="ui",
        title="Timeout test",
        priority="high",
        definition=UITestDefinition(
            id="TIMEOUT-001",
            title="Timeout test",
            steps=[UITestStep(action="click", selector={"strategy": "id", "value": "nonexistent"}, timeout_ms=5000)],
            expected=[UIAssertion(assertion="page_loaded")],
        ).model_dump(mode="json"),
    )
    db.add(tc)
    await db.commit()

    result = await executor.execute_test(
        base_url="http://127.0.0.1:3000",
        run_id=sample_run.id,
        session_id="sess-abc",
        test_case=tc,
    )

    assert result.status == TestResultStatus.TIMEOUT
    assert "timed out" in (result.error or "").lower()

