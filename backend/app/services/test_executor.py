"""Phase 3 Test Executor Dispatcher.
Validates test definitions, enforces safety and limits, dispatches to in-sandbox runners,
and persists TestResults linked to SQLite and Evidence.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.test_case import TestCase, TestResult
from app.models.test_run import TestRun
from app.schemas.test_case import (
    validate_test_definition,
    TestExecutionResult,
    TestResultStatus,
    UITestDefinition,
    APITestDefinition,
)
from app.services.api_tester import APITester
from app.services.evidence_manager import EvidenceManager
from app.services.playwright_runner import PlaywrightRunner

logger = logging.getLogger("testq.test_executor")


class TestExecutor:
    """Dispatches validated tests to appropriate orchestrators and records results."""
    __test__ = False

    def __init__(self, db: AsyncSession, sandbox, container_id: str, control, blocking):
        self.db = db
        self.sandbox = sandbox
        self.container_id = container_id
        self.control = control
        self.blocking = blocking
        self.evidence_mgr = EvidenceManager(db)
        self.playwright_runner = PlaywrightRunner(sandbox, container_id, control, blocking, self.evidence_mgr)
        self.api_tester = APITester(sandbox, container_id, control, blocking, self.evidence_mgr)

    async def execute_test(
        self,
        base_url: str,
        run_id: str,
        session_id: str,
        test_case: TestCase,
        limits: dict | None = None,
    ) -> TestResult:
        """Validate and execute a single test case."""
        limits = limits or {}
        max_steps = limits.get("max_steps_per_test", settings.max_steps_per_test)

        test_result = TestResult(
            run_id=run_id,
            test_case_id=test_case.id,
            status=TestResultStatus.ERROR,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(test_result)
        await self.db.commit()

        # Check early cancellation
        if self.control.cancel_event.is_set():
            test_result.status = TestResultStatus.CANCELLED
            test_result.finished_at = datetime.now(timezone.utc)
            test_result.error = "Test run cancelled before execution"
            await self.db.commit()
            return test_result

        # 1. Parse and strictly validate definition
        try:
            parsed_def = validate_test_definition(test_case.definition)
        except Exception as ve:
            test_result.status = TestResultStatus.ERROR
            test_result.finished_at = datetime.now(timezone.utc)
            test_result.error = f"Invalid test definition schema: {ve}"
            await self.db.commit()
            return test_result

        # 2. Check limits
        if isinstance(parsed_def, UITestDefinition):
            if len(parsed_def.steps) > max_steps:
                test_result.status = TestResultStatus.ERROR
                test_result.finished_at = datetime.now(timezone.utc)
                test_result.error = f"Step count {len(parsed_def.steps)} exceeds maximum allowed ({max_steps})"
                await self.db.commit()
                return test_result

        # 3. Dispatch to orchestrator
        exec_result: TestExecutionResult
        try:
            if isinstance(parsed_def, UITestDefinition):
                exec_result = await self.playwright_runner.execute_test(
                    base_url=base_url,
                    run_id=run_id,
                    session_id=session_id,
                    test_def=parsed_def,
                    test_result_id=test_result.id,
                    limits=limits,
                )
            elif isinstance(parsed_def, APITestDefinition):
                exec_result = await self.api_tester.execute_test(
                    base_url=base_url,
                    run_id=run_id,
                    session_id=session_id,
                    test_def=parsed_def,
                    test_result_id=test_result.id,
                    limits=limits,
                )
            else:
                raise ValueError(f"Unsupported test definition type: {type(parsed_def)}")

        except Exception as exc:
            test_result.status = TestResultStatus.ERROR
            test_result.finished_at = datetime.now(timezone.utc)
            test_result.error = f"Execution error: {exc}"
            await self.db.commit()
            return test_result

        # 4. Update persisted TestResult
        test_result.status = exec_result.status
        test_result.started_at = exec_result.started_at
        test_result.finished_at = exec_result.finished_at
        test_result.duration_ms = exec_result.duration_ms
        test_result.steps_json = [s.model_dump() for s in exec_result.steps]
        test_result.assertions_json = [a.model_dump() for a in exec_result.assertions]
        test_result.error = exec_result.error
        test_result.http_status = getattr(exec_result, "http_status", None)
        await self.db.commit()
        return test_result

    async def execute_suite(
        self,
        base_url: str,
        run_id: str,
        session_id: str,
        test_cases: Sequence[TestCase],
        limits: dict | None = None,
    ) -> list[TestResult]:
        """Execute a sequence of test cases, enforcing max tests limit and recording run stats."""
        limits = limits or {}
        max_tests = limits.get("max_tests_per_run", settings.max_tests_per_run)

        # Enforce max tests per run
        tests_to_run = list(test_cases)[:max_tests]
        results: list[TestResult] = []

        for tc in tests_to_run:
            if self.control.cancel_event.is_set():
                # Record cancelled result for remaining
                cancelled_res = TestResult(
                    run_id=run_id,
                    test_case_id=tc.id,
                    status=TestResultStatus.CANCELLED,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    error="Test run cancelled",
                )
                self.db.add(cancelled_res)
                await self.db.commit()
                results.append(cancelled_res)
                break

            result = await self.execute_test(
                base_url=base_url,
                run_id=run_id,
                session_id=session_id,
                test_case=tc,
                limits=limits,
            )
            results.append(result)

        # Phase 4.6 Deterministic replay mechanism for reproduction counter (Run 1, 2, 3)
        for result in results:
            if result.status in (TestResultStatus.FAIL, TestResultStatus.ERROR) and not self.control.cancel_event.is_set():
                tc = next((c for c in tests_to_run if c.id == result.test_case_id), None)
                if tc:
                    repro_failed = 1  # Run 1 already failed
                    total_runs = 3
                    for _ in range(2, total_runs + 1):
                        if self.control.cancel_event.is_set():
                            break
                        try:
                            parsed_def = validate_test_definition(tc.definition)
                            if isinstance(parsed_def, UITestDefinition):
                                rep_res = await self.playwright_runner.execute_test(
                                    base_url=base_url,
                                    run_id=run_id,
                                    session_id=session_id,
                                    test_def=parsed_def,
                                    test_result_id=result.id,
                                    limits=limits,
                                )
                            else:
                                rep_res = await self.api_tester.execute_test(
                                    base_url=base_url,
                                    run_id=run_id,
                                    session_id=session_id,
                                    test_def=parsed_def,
                                    test_result_id=result.id,
                                    limits=limits,
                                )
                            if rep_res.status in (TestResultStatus.FAIL, TestResultStatus.ERROR):
                                repro_failed += 1
                        except Exception:
                            await self.db.rollback()
                    result.reproduction_count = repro_failed
                    result.reproduction_total = total_runs
                    result.confirmed = (repro_failed == total_runs)
                    try:
                        await self.db.commit()
                    except Exception:
                        await self.db.rollback()

        # Update test run totals
        run_row = (await self.db.execute(select(TestRun).where(TestRun.id == run_id))).scalar_one_or_none()
        if run_row:
            run_row.total_tests = len(results)
            run_row.passed_tests = sum(1 for r in results if r.status == TestResultStatus.PASS)
            run_row.failed_tests = sum(
                1 for r in results if r.status in (TestResultStatus.FAIL, TestResultStatus.ERROR, TestResultStatus.TIMEOUT)
            )
            await self.db.commit()

        return results
