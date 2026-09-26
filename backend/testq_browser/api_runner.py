"""In-sandbox HTTPX API test runner.
Runs inside the TestQ sandbox container, executing deterministic API tests against 127.0.0.1:<port>.
Strictly enforces local loopback / target application origin.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from testq_browser.test_schemas import (
    APITestDefinition,
    APIAssertion,
    AssertionResult,
    StepResult,
    TestExecutionResult,
    TestResultStatus,
)
from testq_browser.policies import same_origin, redact


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_json_path(data: Any, path: str) -> tuple[bool, Any]:
    """Resolve a dot/bracket separated JSON path like 'items[0].id' or 'data.user'."""
    # Split by dot and handle bracket indices
    parts = []
    for token in path.split("."):
        sub_tokens = []
        cur = ""
        for ch in token:
            if ch == "[":
                if cur:
                    sub_tokens.append(cur)
                    cur = ""
            elif ch == "]":
                if cur:
                    sub_tokens.append(int(cur) if cur.isdigit() else cur)
                    cur = ""
            else:
                cur += ch
        if cur:
            sub_tokens.append(int(cur) if cur.isdigit() else cur)
        parts.extend(sub_tokens)

    current = data
    for part in parts:
        if isinstance(part, int):
            if isinstance(current, (list, tuple)) and 0 <= part < len(current):
                current = current[part]
            else:
                return False, None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False, None
    return True, current


class APITestRunner:
    """Executes a single APITestDefinition deterministically via HTTPX inside sandbox."""

    def __init__(self, base_url: str, run_id: str, session_id: str, test_def: APITestDefinition,
                 output_dir: Path, limits: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.session_id = session_id
        self.test_def = test_def
        self.output_dir = output_dir
        self.limits = limits or {}
        self.evidence_files: list[str] = []

    async def run(self) -> TestExecutionResult:
        started_at = _utc_now()
        t0 = time.monotonic()
        req_spec = self.test_def.request

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Target URL validation
        if req_spec.path.startswith(("http://", "https://", "//")):
            finished_at = _utc_now()
            return TestExecutionResult(
                test_id=self.test_def.id,
                run_id=self.run_id,
                status=TestResultStatus.ERROR,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=0.0,
                error="External destinations strictly prohibited in API tests",
            )

        target_path = req_spec.path if req_spec.path.startswith("/") else f"/{req_spec.path}"
        full_url = f"{self.base_url}{target_path}"

        if not same_origin(full_url, self.base_url):
            finished_at = _utc_now()
            return TestExecutionResult(
                test_id=self.test_def.id,
                run_id=self.run_id,
                status=TestResultStatus.ERROR,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=0.0,
                error="Target URL leaves target application origin (external destinations forbidden)",
            )

        step_results: list[StepResult] = []
        assertion_results: list[AssertionResult] = []
        status = TestResultStatus.PASS
        error_msg: str | None = None
        resp_data: dict[str, Any] = {}

        try:
            timeout_sec = (req_spec.timeout_ms or 5000) / 1000.0
            st_step = time.monotonic()

            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout_sec, follow_redirects=False) as client:
                body_kwargs: dict[str, Any] = {}
                if req_spec.body is not None:
                    if isinstance(req_spec.body, (dict, list)):
                        body_kwargs["json"] = req_spec.body
                    elif isinstance(req_spec.body, str):
                        body_kwargs["content"] = req_spec.body.encode("utf-8")

                resp = await client.request(
                    method=req_spec.method,
                    url=target_path,
                    headers=req_spec.headers,
                    params=req_spec.query,
                    **body_kwargs,
                )

            req_duration_ms = (time.monotonic() - st_step) * 1000
            step_results.append(StepResult(
                action=req_spec.method,
                target=target_path,
                status="ok",
                duration_ms=round(req_duration_ms, 2),
            ))

            resp_status_code = resp.status_code
            resp_content_type = resp.headers.get("content-type", "")
            resp_text = resp.text[:50000]
            resp_json = None
            try:
                resp_json = resp.json()
            except Exception:
                pass

            resp_data = {
                "request": {
                    "method": req_spec.method,
                    "url": full_url,
                    "headers": req_spec.headers,
                    "query": req_spec.query,
                    "body": req_spec.body,
                },
                "response": {
                    "status_code": resp_status_code,
                    "headers": dict(resp.headers),
                    "body": redact(resp_text, 10000),
                    "duration_ms": round(req_duration_ms, 2),
                }
            }

            # 2. Evaluate Assertions
            for ast in self.test_def.expected:
                ast_name = ast.assertion
                exp_val = ast.expected

                if ast_name == "status_code":
                    passed = (resp_status_code == int(exp_val))
                    assertion_results.append(AssertionResult(
                        assertion=ast_name, passed=passed,
                        expected=str(exp_val), actual=str(resp_status_code)
                    ))
                    if not passed and status == TestResultStatus.PASS:
                        status = TestResultStatus.FAIL
                        error_msg = f"Status code mismatch: expected {exp_val}, got {resp_status_code}"

                elif ast_name == "response_time":
                    passed = (req_duration_ms <= float(exp_val))
                    assertion_results.append(AssertionResult(
                        assertion=ast_name, passed=passed,
                        expected=f"<={exp_val}ms", actual=f"{round(req_duration_ms, 2)}ms"
                    ))
                    if not passed and status == TestResultStatus.PASS:
                        status = TestResultStatus.FAIL
                        error_msg = f"Response time exceeded: expected <={exp_val}ms, got {round(req_duration_ms, 2)}ms"

                elif ast_name == "content_type":
                    passed = (str(exp_val).lower() in resp_content_type.lower())
                    assertion_results.append(AssertionResult(
                        assertion=ast_name, passed=passed,
                        expected=str(exp_val), actual=resp_content_type
                    ))
                    if not passed and status == TestResultStatus.PASS:
                        status = TestResultStatus.FAIL
                        error_msg = f"Content-Type mismatch: expected {exp_val}, got {resp_content_type}"

                elif ast_name == "json_field_present":
                    if resp_json is None:
                        passed = False
                        actual_str = "non-json response"
                    else:
                        found, _ = _resolve_json_path(resp_json, ast.field or "")
                        passed = found
                        actual_str = "field present" if found else "field missing"

                    assertion_results.append(AssertionResult(
                        assertion=ast_name, passed=passed,
                        expected=f"field '{ast.field}' present", actual=actual_str
                    ))
                    if not passed and status == TestResultStatus.PASS:
                        status = TestResultStatus.FAIL
                        error_msg = f"Expected JSON field '{ast.field}' not found in response"

                elif ast_name == "json_value":
                    if resp_json is None:
                        passed = False
                        actual_str = "non-json response"
                    else:
                        found, val = _resolve_json_path(resp_json, ast.field or "")
                        if not found:
                            passed = False
                            actual_str = "field missing"
                        else:
                            passed = (str(val) == str(exp_val) or val == exp_val)
                            actual_str = str(val)

                    assertion_results.append(AssertionResult(
                        assertion=ast_name, passed=passed,
                        expected=f"{ast.field} == {exp_val}", actual=actual_str
                    ))
                    if not passed and status == TestResultStatus.PASS:
                        status = TestResultStatus.FAIL
                        error_msg = f"Expected JSON field '{ast.field}' value {exp_val}, got {actual_str}"

                else:
                    assertion_results.append(AssertionResult(
                        assertion=ast_name, passed=False, error=f"Unknown assertion: {ast_name}"
                    ))
                    if status == TestResultStatus.PASS:
                        status = TestResultStatus.ERROR
                        error_msg = f"Unknown assertion: {ast_name}"

        except httpx.TimeoutException as te:
            status = TestResultStatus.TIMEOUT
            error_msg = f"API request timed out: {te}"
            step_results.append(StepResult(
                action=req_spec.method, target=target_path, status="timeout", error=error_msg
            ))
        except asyncio.CancelledError:
            status = TestResultStatus.CANCELLED
            error_msg = "API test cancelled"
        except Exception as e:
            status = TestResultStatus.ERROR
            error_msg = redact(str(e))
            step_results.append(StepResult(
                action=req_spec.method, target=target_path, status="error", error=error_msg
            ))

        duration_ms = (time.monotonic() - t0) * 1000
        finished_at = _utc_now()

        # Save API exchange evidence
        evidence_filename = f"api_exchange_{self.test_def.id}.json"
        try:
            (self.output_dir / evidence_filename).write_text(
                json.dumps(resp_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.evidence_files.append(evidence_filename)
        except Exception:
            pass

        result = TestExecutionResult(
            test_id=self.test_def.id,
            run_id=self.run_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round(duration_ms, 2),
            steps=step_results,
            assertions=assertion_results,
            error=error_msg,
            evidence_files=self.evidence_files,
        )

        result_filename = f"result_{self.test_def.id}.json"
        try:
            (self.output_dir / result_filename).write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            self.evidence_files.append(result_filename)
        except Exception:
            pass

        return result


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python -m testq_browser.api_runner <base64_payload>\n")
        return 1

    payload_json = base64.b64decode(sys.argv[1]).decode("utf-8")
    data = json.loads(payload_json)

    base_url = data["base_url"]
    run_id = data["run_id"]
    session_id = data["session_id"]
    test_def = APITestDefinition.model_validate(data["test_definition"])
    output_dir = Path(data.get("output_dir", f"/discovery/{session_id}"))
    limits = data.get("limits", {})

    runner = APITestRunner(base_url, run_id, session_id, test_def, output_dir, limits)
    result = asyncio.run(runner.run())
    sys.stdout.write(result.model_dump_json() + "\n")
    return 0 if result.status == TestResultStatus.PASS else (2 if result.status == TestResultStatus.FAIL else 1)


if __name__ == "__main__":
    raise SystemExit(main())
