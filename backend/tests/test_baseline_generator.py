"""Tests for Phase 3 Deterministic Baseline Test Generator."""
import pytest

from app.schemas.test_case import validate_test_definition
from app.services.baseline_generator import BaselineGenerator
from testq_browser.schemas import (
    ApplicationMap,
    PageRecord,
    Form,
    Element,
    SelectorCandidate,
    APIEndpoint,
)


def _sample_app_map() -> ApplicationMap:
    return ApplicationMap(
        run_id="run-1",
        session_id="sess-1",
        base_url="http://127.0.0.1:3000",
        pages=[
            PageRecord(
                url="http://127.0.0.1:3000/",
                depth=0,
                forms=[Form(identifier="login-form", action="/login", method="POST")],
                inputs=[
                    Element(
                        tag="input",
                        selectors=[
                            SelectorCandidate(strategy="test_id", value="email-input"),
                            SelectorCandidate(strategy="id", value="email"),
                        ],
                    )
                ],
            ),
            PageRecord(
                url="http://127.0.0.1:3000/dashboard",
                depth=1,
            ),
            PageRecord(
                url="http://127.0.0.1:3000/settings",
                depth=1,
            ),
        ],
        api_endpoints=[
            APIEndpoint(path="/api/v1/user", method="GET"),
            APIEndpoint(path="/api/v1/health", method="GET"),
        ],
    )


def test_baseline_generator_creates_expected_suite():
    app_map = _sample_app_map()
    suite = BaselineGenerator.generate_suite(app_map, run_id="run-1")

    assert len(suite) >= 4

    # 1. HOME-001 exists
    home_cases = [tc for tc in suite if tc.definition["id"] == "HOME-001"]
    assert len(home_cases) == 1
    assert home_cases[0].type == "ui"
    assert home_cases[0].priority == "critical"

    # 2. NAV routes exist
    nav_cases = [tc for tc in suite if tc.definition["id"].startswith("NAV-")]
    assert len(nav_cases) == 2  # /dashboard and /settings

    # 3. Form or input UI test exists
    ui_cases = [tc for tc in suite if tc.definition["id"].startswith("UI-")]
    assert len(ui_cases) >= 1

    # 4. API tests exist
    api_cases = [tc for tc in suite if tc.definition["id"].startswith("API-")]
    assert len(api_cases) == 2


def test_all_generated_tests_strictly_validate():
    app_map = _sample_app_map()
    suite = BaselineGenerator.generate_suite(app_map, run_id="run-1")

    for tc in suite:
        parsed = validate_test_definition(tc.definition)
        assert parsed.id == tc.definition["id"]


def test_baseline_generator_is_deterministic():
    app_map = _sample_app_map()
    suite1 = BaselineGenerator.generate_suite(app_map, run_id="run-1")
    suite2 = BaselineGenerator.generate_suite(app_map, run_id="run-1")

    assert len(suite1) == len(suite2)
    for c1, c2 in zip(suite1, suite2):
        assert c1.definition == c2.definition
        assert c1.title == c2.title
        assert c1.type == c2.type
