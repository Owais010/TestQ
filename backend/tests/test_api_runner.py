"""Tests for in-sandbox HTTPX API runner."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.schemas.test_case import (
    APITestDefinition,
    APIRequestSpec,
    APIAssertion,
    TestResultStatus,
)
from testq_browser.api_runner import APITestRunner, _resolve_json_path


def test_resolve_json_path():
    data = {
        "user": {
            "name": "Alice",
            "roles": ["admin", "editor"],
            "settings": {"theme": "dark"},
        },
        "items": [
            {"id": 101, "title": "First"},
            {"id": 102, "title": "Second"},
        ],
    }
    found, val = _resolve_json_path(data, "user.name")
    assert found is True
    assert val == "Alice"

    found, val = _resolve_json_path(data, "user.roles[0]")
    assert found is True
    assert val == "admin"

    found, val = _resolve_json_path(data, "items[1].id")
    assert found is True
    assert val == 102

    found, val = _resolve_json_path(data, "user.nonexistent")
    assert found is False

    found, val = _resolve_json_path(data, "items[5].id")
    assert found is False


@pytest.mark.asyncio
async def test_api_runner_success(tmp_path: Path):
    test_def = APITestDefinition(
        id="API-001",
        title="Check status and json",
        priority="high",
        request=APIRequestSpec(
            method="GET",
            path="/api/health",
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
            APIAssertion(assertion="content_type", expected="application/json"),
            APIAssertion(assertion="json_field_present", field="status"),
            APIAssertion(assertion="json_value", field="status", expected="ok"),
        ],
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.text = '{"status": "ok", "uptime": 123}'
    mock_resp.json.return_value = {"status": "ok", "uptime": 123}

    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=mock_resp)):
        runner = APITestRunner(
            base_url="http://127.0.0.1:8000",
            run_id="run-1",
            session_id="sess-1",
            test_def=test_def,
            output_dir=tmp_path,
        )
        res = await runner.run()

    assert res.status == TestResultStatus.PASS
    assert len(res.assertions) == 4
    assert all(a.passed for a in res.assertions)
    assert (tmp_path / "result_API-001.json").exists()
    assert (tmp_path / "api_exchange_API-001.json").exists()


@pytest.mark.asyncio
async def test_api_runner_assertion_failure(tmp_path: Path):
    test_def = APITestDefinition(
        id="API-002",
        title="Mismatch test",
        priority="high",
        request=APIRequestSpec(
            method="GET",
            path="/api/check",
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
        ],
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.headers = {"content-type": "text/plain"}
    mock_resp.text = "Internal Server Error"
    mock_resp.json.side_effect = Exception("not json")

    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=mock_resp)):
        runner = APITestRunner(
            base_url="http://127.0.0.1:8000",
            run_id="run-1",
            session_id="sess-1",
            test_def=test_def,
            output_dir=tmp_path,
        )
        res = await runner.run()

    assert res.status == TestResultStatus.FAIL
    assert len(res.assertions) == 1
    assert res.assertions[0].passed is False
    assert "Status code mismatch" in (res.error or "")


@pytest.mark.asyncio
async def test_api_runner_timeout(tmp_path: Path):
    test_def = APITestDefinition(
        id="API-003",
        title="Timeout test",
        priority="medium",
        request=APIRequestSpec(
            method="GET",
            path="/api/slow",
            timeout_ms=1000,
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
        ],
    )

    with patch("httpx.AsyncClient.request", new=AsyncMock(side_effect=httpx.TimeoutException("Read timeout"))):
        runner = APITestRunner(
            base_url="http://127.0.0.1:8000",
            run_id="run-1",
            session_id="sess-1",
            test_def=test_def,
            output_dir=tmp_path,
        )
        res = await runner.run()

    assert res.status == TestResultStatus.TIMEOUT
    assert "timed out" in (res.error or "").lower()


@pytest.mark.asyncio
async def test_api_runner_rejects_external_target(tmp_path: Path):
    test_def = APITestDefinition(
        id="API-004",
        title="External target",
        priority="critical",
        request=APIRequestSpec(
            method="GET",
            path="/forbidden",
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
        ],
    )

    runner = APITestRunner(
        base_url="http://127.0.0.1:8000",
        run_id="run-1",
        session_id="sess-1",
        test_def=test_def,
        output_dir=tmp_path,
    )
    with patch("testq_browser.api_runner.same_origin", return_value=False):
        res = await runner.run()

    assert res.status == TestResultStatus.ERROR
    assert "origin" in (res.error or "").lower()


@pytest.mark.asyncio
async def test_api_runner_response_time_pass(tmp_path: Path):
    """Test that response_time assertion PASSES when response is faster than threshold."""
    test_def = APITestDefinition(
        id="API-RT-PASS",
        title="Response time passes",
        priority="high",
        request=APIRequestSpec(method="GET", path="/api/fast"),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
            APIAssertion(assertion="response_time", expected=5000),  # 5000ms threshold
        ],
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.text = '{"status": "fast"}'
    mock_resp.json.return_value = {"status": "fast"}

    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=mock_resp)):
        runner = APITestRunner(
            base_url="http://127.0.0.1:8000",
            run_id="run-1",
            session_id="sess-1",
            test_def=test_def,
            output_dir=tmp_path,
        )
        res = await runner.run()

    assert res.status == TestResultStatus.PASS
    rt_assertion = [a for a in res.assertions if a.assertion == "response_time"][0]
    assert rt_assertion.passed is True


@pytest.mark.asyncio
async def test_api_runner_response_time_fail(tmp_path: Path):
    """Test that response_time assertion FAILS when duration exceeds threshold."""
    test_def = APITestDefinition(
        id="API-RT-FAIL",
        title="Response time fails",
        priority="high",
        request=APIRequestSpec(method="GET", path="/api/slow-threshold"),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
            APIAssertion(assertion="response_time", expected=0.001),  # tiny 0.001ms threshold -> will fail
        ],
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.text = '{"status": "ok"}'
    mock_resp.json.return_value = {"status": "ok"}

    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=mock_resp)):
        runner = APITestRunner(
            base_url="http://127.0.0.1:8000",
            run_id="run-1",
            session_id="sess-1",
            test_def=test_def,
            output_dir=tmp_path,
        )
        res = await runner.run()

    assert res.status == TestResultStatus.FAIL
    rt_assertion = [a for a in res.assertions if a.assertion == "response_time"][0]
    assert rt_assertion.passed is False
    assert "Response time exceeded" in (res.error or "")


@pytest.mark.parametrize("bad_path", [
    "https://example.com/api",
    "http://example.com/api",
    "//example.com/api",
    "http://127.0.0.1:9999/api",
])
def test_api_request_spec_rejects_external_and_absolute_paths(bad_path: str):
    """Verify Pydantic schema validation strictly rejects absolute URLs and protocol-relative paths."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc:
        APIRequestSpec(method="GET", path=bad_path)
    assert any(term in str(exc.value).lower() for term in ("relative", "prohibited", "must start with /"))


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_path", [
    "https://example.com/api",
    "http://example.com/api",
    "//example.com/api",
])
async def test_api_runner_defense_in_depth_rejects_escapes(tmp_path: Path, bad_path: str):
    """Verify in-sandbox runner defense-in-depth catches unvalidated escape attempts."""
    # Construct without validation to test runner's own internal defense-in-depth
    req = APIRequestSpec.model_construct(method="GET", path=bad_path, headers={}, query={}, body=None, timeout_ms=5000)
    test_def = APITestDefinition.model_construct(
        id="API-ESCAPE",
        type="api",
        title="Escape attempt",
        priority="critical",
        request=req,
        expected=[APIAssertion.model_construct(assertion="status_code", expected=200)],
    )

    runner = APITestRunner(
        base_url="http://127.0.0.1:8000",
        run_id="run-1",
        session_id="sess-1",
        test_def=test_def,
        output_dir=tmp_path,
    )
    res = await runner.run()
    assert res.status == TestResultStatus.ERROR
    assert ("external destinations" in (res.error or "").lower() or
            "origin" in (res.error or "").lower())


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_path", [
    "https://example.com/api",
    "//example.com/api",
])
async def test_host_api_tester_rejects_external_paths(bad_path: str):
    """Verify host APITester rejects external destinations before execution."""
    from app.services.api_tester import APITester, APITesterError

    sandbox = MagicMock()
    control = MagicMock()
    evidence_mgr = MagicMock()
    tester = APITester(sandbox, "container-1", control, AsyncMock(), evidence_mgr)

    req = APIRequestSpec.model_construct(method="GET", path=bad_path, headers={}, query={}, body=None, timeout_ms=5000)
    test_def = APITestDefinition.model_construct(
        id="API-HOST-ESCAPE",
        type="api",
        title="Host escape attempt",
        priority="critical",
        request=req,
        expected=[APIAssertion.model_construct(assertion="status_code", expected=200)],
    )

    with pytest.raises(APITesterError) as exc_info:
        await tester.execute_test(
            base_url="http://127.0.0.1:8000",
            run_id="run-1",
            session_id="sess-1",
            test_def=test_def,
            test_result_id="res-1",
        )
    assert ("external destinations" in str(exc_info.value).lower() or
            "leaves target application origin" in str(exc_info.value).lower())

