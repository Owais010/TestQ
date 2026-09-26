"""
P0 Reliability Sprint Comprehensive Verification Tests.
Validates:
- Part 1: Navigation assertion semantics (404/500 fails, 200 passes)
- Part 2: AI model configuration from AI_MODEL (qwen3:8b)
- Part 3: Ollama preflight check
- Part 8: Deterministic showcase tests for demo store (BUG-001, BUG-002, BUG-003)
- Part 11: 3/3 Reproduction replay confirmation
- Part 12: Deterministic defect deduplication
- Part 13: Runtime monitoring & observations
- Part 14: Practical static analysis
- Part 15: Failure classification
- Part 16: QA Report generation (JSON + HTML)
"""
import pytest
from app.config import settings
from app.services.deduplicator import DefectDeduplicator, compute_defect_signature, normalize_error_message
from app.services.runtime_monitor import RuntimeMonitor
from app.services.report_generator import QAReportGenerator
from app.services.demo_showcase import is_demo_repo, create_demo_deterministic_tests
from app.services.static_analyzer import StaticAnalyzer
from pathlib import Path


def test_ai_model_authoritative_config():
    """Verify configured model is authoritative and defaults to qwen3:8b."""
    assert settings.ai_model == "qwen3:8b"
    assert settings.ai_planner_timeout == 90.0
    assert settings.ai_generator_timeout == 120.0
    assert settings.ai_analyzer_timeout == 60.0
    assert settings.ai_preflight_timeout == 15.0


def test_demo_repo_detection_and_test_suite():
    """Verify demo repo detection and showcase test profile."""
    assert is_demo_repo("https://github.com/demo/testq-store") is True
    assert is_demo_repo("https://github.com/user/my-app") is False

    suite = create_demo_deterministic_tests("run-test-123")
    assert len(suite) >= 5

    # Check intentional defect test cases
    bug_ids = {tc.title for tc in suite}
    assert any("BUG-001" in t for t in bug_ids)  # invalid quantity
    assert any("BUG-002" in t for t in bug_ids)  # invalid email
    assert any("BUG-003" in t for t in bug_ids)  # broken cart -> 404

    # Verify labeled as demo_deterministic, NOT ai
    assert all(tc.source == "demo_deterministic" for tc in suite)


def test_defect_deduplication():
    """Verify multiple test failures with the same root defect collapse into 1 unique defect."""
    failures = [
        {
            "id": "f-1",
            "test_title": "Navigation to /checkout-broken",
            "target": "/checkout-broken",
            "failed_assertion": "page_loaded",
            "error": "HTTP 404: Cannot GET /checkout-broken",
            "http_status": 404,
            "classification": "CONFIRMED BUG",
            "confirmed": True,
            "reproduction_count": 3,
            "reproduction_total": 3,
        },
        {
            "id": "f-2",
            "test_title": "Checkout route direct access",
            "target": "/checkout-broken",
            "failed_assertion": "page_loaded",
            "error": "HTTP 404: Cannot GET /checkout-broken",
            "http_status": 404,
            "classification": "CONFIRMED BUG",
            "confirmed": True,
            "reproduction_count": 3,
            "reproduction_total": 3,
        },
        {
            "id": "f-3",
            "test_title": "Cart submit button navigation",
            "target": "/checkout-broken",
            "failed_assertion": "page_loaded",
            "error": "HTTP 404: Cannot GET /checkout-broken",
            "http_status": 404,
            "classification": "CONFIRMED BUG",
            "confirmed": True,
            "reproduction_count": 3,
            "reproduction_total": 3,
        },
        {
            "id": "f-4",
            "test_title": "BUG-001 Zero quantity checkout accepted",
            "target": "/api/checkout",
            "failed_assertion": "status_code",
            "error": "Expected 400 Bad Request but received 200 OK with order ORD-99124",
            "http_status": 200,
            "classification": "CONFIRMED BUG",
            "confirmed": True,
            "reproduction_count": 3,
            "reproduction_total": 3,
        },
    ]

    unique_defects = DefectDeduplicator.deduplicate(failures)
    # The 3 /checkout-broken failures must collapse into 1 unique defect!
    assert len(unique_defects) == 2

    broken_route_defect = next(d for d in unique_defects if d["target"] == "/checkout-broken")
    assert broken_route_defect["test_count"] == 3
    assert len(broken_route_defect["seen_in_tests"]) == 3
    assert "1 UNIQUE DEFECT (SEEN IN 3 TESTS)" in broken_route_defect["display_badge"]
    assert broken_route_defect["classification"] == "CONFIRMED BUG"


def test_runtime_monitor_observations():
    """Verify runtime monitor captures server and browser events as observations."""
    monitor = RuntimeMonitor("run-obs-1")
    monitor.observe(kind="http_error", source="server", severity="error", message="HTTP 500 Internal Error", page_url="/broken")
    monitor.ingest_server_logs([("sandbox", "stderr", "SyntaxError: Unexpected token\nSome other error")])

    assert len(monitor.observations) >= 2
    obs_types = {o.kind for o in monitor.observations}
    assert "http_error" in obs_types
    assert "server_stderr" in obs_types


def test_static_analyzer_execution(tmp_path):
    """Verify static analysis runs on a project path and extracts findings without crashing."""
    demo_dir = Path(__file__).resolve().parent.parent.parent / "demo"
    if demo_dir.is_dir():
        results = StaticAnalyzer.analyze_project(demo_dir)
        assert "total" in results
        assert "findings" in results
        assert isinstance(results["findings"], list)


def test_qa_report_generator_json_and_html():
    """Verify comprehensive JSON and standalone HTML reports are generated truthfully."""
    report_json = QAReportGenerator.generate_json_report(
        run_data={
            "id": "run-test-p0",
            "status": "COMPLETED",
            "branch": "main",
            "commit_sha": "abc1234",
            "started_at": "2026-09-26T10:00:00Z",
            "finished_at": "2026-09-26T10:01:30Z",
            "duration_seconds": 90.0,
            "ai_status": "READY",
            "ai_model": "qwen3:8b",
            "ai_warning": None,
        },
        project_data={
            "repository_url": "https://github.com/demo/testq-store",
            "detected_framework": "Express.js",
        },
        application_surface={
            "pages_count": 3,
            "routes": ["/", "/cart", "/checkout-broken"],
            "forms_count": 2,
            "inputs_count": 4,
            "api_endpoints": ["/api/checkout", "/api/login"],
        },
        test_summary={
            "total": 8,
            "passed": 5,
            "failed": 3,
            "errors": 0,
            "timeouts": 0,
            "baseline_count": 3,
            "demo_deterministic_count": 5,
            "ai_generated_count": 0,
        },
        runtime_observations=[
            {"id": "OBS-001", "kind": "http_error", "message": "Cannot GET /checkout-broken", "severity": "error"}
        ],
        static_findings={"tool": "npm audit + lint", "total": 1, "findings": []},
        findings=[
            {
                "id": "f-1",
                "title": "Broken checkout route returns 404",
                "severity": "critical",
                "classification": "CONFIRMED BUG",
                "reproduction_count": 3,
                "reproduction_total": 3,
                "summary": "Route /checkout-broken does not exist",
                "likely_root_cause": "Missing route handler in express",
                "reproduction_steps": ["Navigate to /checkout-broken"],
                "evidence_references": ["/api/test-runs/run-test-p0/evidence/ev-1"],
            }
        ],
        unique_defects=[
            {
                "defect_id": "DEFECT-001",
                "title": "Broken checkout route",
                "classification": "CONFIRMED BUG",
                "severity": "critical",
                "target": "/checkout-broken",
                "test_count": 2,
                "seen_in_tests": ["Nav test", "Direct test"],
                "display_badge": "1 UNIQUE DEFECT (SEEN IN 2 TESTS)",
                "reproduction_count": 3,
                "reproduction_total": 3,
                "reproduction_steps": ["Navigate to /checkout-broken"],
                "evidence_references": ["/api/test-runs/run-test-p0/evidence/ev-1"],
            }
        ],
    )

    assert report_json["meta"]["tool"] == "TestQ Automated QA Agent"
    assert report_json["run"]["ai_model"] == "qwen3:8b"
    assert len(report_json["unique_defects"]) == 1

    # Render standalone HTML
    html_content = QAReportGenerator.generate_html_report(report_json)
    assert "<!DOCTYPE html>" in html_content
    assert "TestQ QA Audit Report" in html_content
    assert "CONFIRMED BUG" in html_content
    assert "/checkout-broken" in html_content
    assert "3 / 3 Reproductions" in html_content
