"""Host orchestration of the in-sandbox Playwright test runner."""
from __future__ import annotations

import base64
import json
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.schemas.test_case import (
    UITestDefinition,
    TestExecutionResult,
    TestResultStatus,
)
from app.services.evidence_manager import EvidenceManager
from testq_browser.policies import redact


class PlaywrightRunnerError(RuntimeError):
    pass


class PlaywrightRunner:
    """Host-side orchestrator for running in-sandbox Playwright tests."""

    def __init__(self, sandbox, container_id: str, control, blocking, evidence_manager: EvidenceManager):
        self.sandbox = sandbox
        self.container_id = container_id
        self.control = control
        self.blocking = blocking
        self.evidence = evidence_manager

    async def execute_test(
        self,
        base_url: str,
        run_id: str,
        session_id: str,
        test_def: UITestDefinition,
        test_result_id: str,
        limits: dict | None = None,
    ) -> TestExecutionResult:
        """Execute a UI test inside the sandbox and export verified evidence."""
        limits = limits or {
            "test_timeout": settings.test_timeout,
            "action_timeout": settings.test_action_timeout,
            "navigation_timeout": settings.navigation_timeout,
        }

        payload_dict = {
            "base_url": base_url,
            "run_id": run_id,
            "session_id": session_id,
            "test_definition": test_def.model_dump(mode="json"),
            "output_dir": f"/discovery/{session_id}",
            "limits": limits,
        }
        payload_b64 = base64.b64encode(json.dumps(payload_dict).encode("utf-8")).decode("ascii")

        cmd = f"/opt/testq/venv/bin/python -I -m testq_browser.test_runner {shlex.quote(payload_b64)}"
        timeout_sec = limits.get("test_timeout", settings.test_timeout) + 15

        error: BaseException | None = None
        execution = None
        t0 = time.monotonic()
        started_at = datetime.now(timezone.utc)

        try:
            execution = await self.blocking(
                self.sandbox.execute,
                self.container_id,
                cmd,
                timeout=timeout_sec,
                working_dir="/opt/testq",
                source=f"test_{test_def.id}",
                user="10002:10002",
                environment={"HOME": "/home/browser", "PYTHONNOUSERSITE": "1"},
            )
        except BaseException as caught:
            error = caught

        # Read result artifact from sandbox
        result_filename = f"result_{test_def.id}.json"
        result: TestExecutionResult | None = None
        try:
            data = await self.blocking(
                self.sandbox.read_artifact,
                self.container_id,
                session_id,
                result_filename,
                settings.discovery_limits().max_artifact_bytes,
            )
            result = TestExecutionResult.model_validate_json(data)
        except Exception as read_err:
            duration_ms = (time.monotonic() - t0) * 1000
            finished_at = datetime.now(timezone.utc)
            status = TestResultStatus.ERROR
            err_msg = f"Failed to read test result: {redact(str(read_err))}"

            if self.control.cancel_event.is_set():
                status = TestResultStatus.CANCELLED
                err_msg = "Test execution cancelled"
            elif error or (execution and execution.timed_out):
                status = TestResultStatus.TIMEOUT
                err_msg = f"Test execution timed out: {redact(str(error)) if error else 'limit exceeded'}"

            result = TestExecutionResult(
                test_id=test_def.id,
                run_id=run_id,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=round(duration_ms, 2),
                error=err_msg,
            )

        if self.control.cancel_event.is_set():
            result.status = TestResultStatus.CANCELLED
            result.error = "Test execution cancelled"
        elif error and not result.error:
            result.status = TestResultStatus.ERROR
            result.error = redact(str(error))

        # Store test evidence
        for filename in result.evidence_files:
            try:
                raw_bytes = await self.blocking(
                    self.sandbox.read_artifact,
                    self.container_id,
                    session_id,
                    filename,
                    settings.discovery_limits().max_artifact_bytes,
                )
                kind = "test_screenshot" if filename.endswith(".png") else (
                    "test_trace" if filename.endswith(".zip") else (
                        "test_console" if "console" in filename else (
                            "test_network" if "network" in filename else "test_result"
                        )
                    )
                )
                await self.evidence.store_test(
                    run_id=run_id,
                    session_id=session_id,
                    test_result_id=test_result_id,
                    filename=filename,
                    kind=kind,
                    data=raw_bytes,
                )
            except Exception as ev_err:
                # Evidence failure shouldn't fail test pass/fail if already determined,
                # but should be recorded in error if none exists
                if not result.error:
                    result.error = f"Evidence export failed: {redact(str(ev_err))}"

        return result
