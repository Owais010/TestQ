"""Tests for Phase 3 deterministic test schemas and validation."""
import pytest
from pydantic import ValidationError

from app.schemas.test_case import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    APITestDefinition,
    APIRequestSpec,
    APIAssertion,
    SelectorSpec,
    TestArtifact,
    TestExecutionResult,
    TestResultStatus,
    validate_test_definition,
)


def test_valid_ui_test_definition():
    data = {
        "id": "HOME-001",
        "type": "ui",
        "title": "Homepage loads successfully",
        "priority": "critical",
        "steps": [
            {"action": "goto", "target": "/"},
            {"action": "wait", "timeout_ms": 500},
        ],
        "expected": [
            {"assertion": "page_loaded"},
            {"assertion": "http_status", "expected": "200"},
        ],
    }
    test_def = validate_test_definition(data)
    assert isinstance(test_def, UITestDefinition)
    assert test_def.id == "HOME-001"
    assert len(test_def.steps) == 2
    assert len(test_def.expected) == 2


def test_ui_test_with_selectors_and_candidates():
    step = UITestStep(
        action="click",
        candidates=[
            SelectorSpec(strategy="test_id", value="submit-btn"),
            SelectorSpec(strategy="role", value="Submit", role="button"),
            SelectorSpec(strategy="css", value="button.submit"),
        ],
    )
    assert len(step.candidates) == 3
    assert step.candidates[0].strategy == "test_id"
    assert step.candidates[1].role == "button"


def test_invalid_ui_action_rejected():
    with pytest.raises(ValidationError):
        UITestStep(action="eval_script", target="alert(1)")


def test_goto_absolute_url_rejected():
    with pytest.raises(ValidationError) as exc:
        UITestStep(action="goto", target="https://evil.com")
    assert "relative path" in str(exc.value)


def test_goto_missing_leading_slash_rejected():
    with pytest.raises(ValidationError) as exc:
        UITestStep(action="goto", target="login")
    assert "start with /" in str(exc.value)


def test_fill_missing_value_rejected():
    with pytest.raises(ValidationError):
        UITestStep(action="fill", target="#username")


def test_click_missing_target_and_selector_rejected():
    with pytest.raises(ValidationError):
        UITestStep(action="click")


def test_role_strategy_requires_role_field():
    with pytest.raises(ValidationError) as exc:
        SelectorSpec(strategy="role", value="Submit")
    assert "requires the 'role' field" in str(exc.value)


def test_valid_api_test_definition():
    data = {
        "id": "API-001",
        "type": "api",
        "title": "API users endpoint responds",
        "priority": "high",
        "request": {
            "method": "GET",
            "path": "/api/users",
            "headers": {"accept": "application/json"},
            "query": {"page": "1"},
        },
        "expected": [
            {"assertion": "status_code", "expected": 200},
            {"assertion": "content_type", "expected": "application/json"},
            {"assertion": "json_field_present", "field": "users"},
        ],
    }
    test_def = validate_test_definition(data)
    assert isinstance(test_def, APITestDefinition)
    assert test_def.request.method == "GET"
    assert len(test_def.expected) == 3


def test_api_path_must_be_relative():
    with pytest.raises(ValidationError) as exc:
        APIRequestSpec(method="GET", path="http://evil.com/leak")
    assert "relative" in str(exc.value)


def test_api_disallows_arbitrary_headers():
    with pytest.raises(ValidationError) as exc:
        APIRequestSpec(
            method="GET",
            path="/api/data",
            headers={"x-malicious-header": "attack"},
        )
    assert "allowlist" in str(exc.value)


def test_malformed_assertion_rejected():
    # json_field_present requires 'field'
    with pytest.raises(ValidationError):
        APIAssertion(assertion="json_field_present")

    # json_value requires 'field' and 'expected'
    with pytest.raises(ValidationError):
        APIAssertion(assertion="json_value", field="user.name")


def test_unknown_test_type_rejected():
    with pytest.raises(ValueError) as exc:
        validate_test_definition({"type": "exploit", "id": "EXP-001"})
    assert "Unknown test type" in str(exc.value)


def test_test_artifact_model_validation():
    art = TestArtifact(
        kind="test_screenshot",
        filename="screenshot_HOME-001.png",
        size_bytes=1024,
        sha256="a" * 64,
        media_type="image/png",
    )
    assert art.kind == "test_screenshot"

    # Reject path traversal in artifact filename
    with pytest.raises(ValidationError):
        TestArtifact(
            kind="test_screenshot",
            filename="../../etc/passwd.png",
            size_bytes=100,
            sha256="a" * 64,
            media_type="image/png",
        )


def test_test_execution_result_statuses():
    for status in ("PASS", "FAIL", "ERROR", "TIMEOUT", "CANCELLED"):
        res = TestExecutionResult(
            test_id="TEST-001",
            run_id="run-123",
            status=status,
            started_at="2026-09-25T12:00:00Z",
            finished_at="2026-09-25T12:00:01Z",
        )
        assert res.status == status

    with pytest.raises(ValidationError):
        TestExecutionResult(
            test_id="TEST-001",
            run_id="run-123",
            status="UNKNOWN_STATUS",
            started_at="2026-09-25T12:00:00Z",
            finished_at="2026-09-25T12:00:01Z",
        )
