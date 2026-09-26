"""Phase 4 real Docker end-to-end tests:
Combines real sandbox discovery, AI test generation, and real Phase 3 deterministic execution.
Gated by TESTQ_DOCKER_TESTS=1.
Optional live Ollama test gated by TESTQ_OLLAMA_TESTS=1.
"""
import hashlib
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.ai.base import AIProvider
from app.ai.ollama import OllamaProvider
from app.config import settings
from app.models.discovery import Evidence
from app.models.test_case import TestCase, TestResult
from app.models.test_run import TestRunStatus as S
from app.schemas.test_case import TestResultStatus
from app.services.test_planner import TestPlanner
from app.services.test_generator import TestGenerator
from app.worker.pipeline import Pipeline
from app.worker.control import RunControl
from tests.test_docker_hardening import git_fixture, LocalGit
from tests.test_hardening import new_run

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("TESTQ_DOCKER_TESTS") != "1", reason="Requires real Docker"
    ),
]


async def test_real_docker_ai_generation_and_execution_pipeline(db, tmp_path, monkeypatch):
    """End-to-end integration test with real Docker sandbox container:
    clone -> build -> start -> discovery -> baseline generation -> AI test generation -> combined execution -> persistence -> cleanup.
    """
    source = git_fixture(tmp_path, "success")
    (source / "server.js").write_text(r"""
const http = require('http');
const port = process.env.PORT || 4321;
const html = `<!doctype html><title>TestQ Phase 4 Fixture</title>
<h1>Phase 4 AI Test Fixture</h1>
<a href="/profile">User Profile</a>
<form id="feedback-form" action="/api/feedback" method="post">
  <input data-testid="comment-input" name="comment" type="text" value="Great app">
  <button id="send-btn" data-testid="send-btn" type="submit">Send Feedback</button>
</form>
<script>
  fetch('/api/status').then(r => r.json());
</script>`;

http.createServer((req, res) => {
  if (req.url === '/api/feedback' && req.method === 'POST') {
    res.setHeader('Content-Type', 'application/json');
    return res.end(JSON.stringify({ status: 'ok', saved: true }));
  }
  if (req.url === '/api/status') {
    res.setHeader('Content-Type', 'application/json');
    return res.end(JSON.stringify({ status: 'healthy', uptime: 100 }));
  }
  if (req.url === '/profile') {
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><title>Profile</title><h1>User Profile Page</h1>');
  }
  res.setHeader('Content-Type', 'text/html');
  res.end(html);
}).listen(port, '127.0.0.1');
""")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(source),
            "-c", "user.name=TestQ",
            "-c", "user.email=testq@example.invalid",
            "commit", "-m", "Phase 4 AI test fixture",
        ],
        check=True,
        capture_output=True,
    )

    evidence_root = Path(os.environ.get("TESTQ_FIXTURE_EVIDENCE_DIR", str(tmp_path / "evidence"))).resolve()
    monkeypatch.setattr(settings, "evidence_dir", evidence_root)

    # Mock the AI provider to reliably return valid structured planning and generation
    mock_ai = AsyncMock(spec=AIProvider)
    mock_ai.generate.side_effect = [
        # Call 1: TestPlanner
        {
            "summary": "AI planned tests for profile and feedback",
            "items": [
                {
                    "id": "STRAT-001",
                    "category": "forms",
                    "target": "/",
                    "description": "Fill and submit feedback form",
                    "risk_level": "medium",
                    "priority": "high",
                },
                {
                    "id": "STRAT-002",
                    "category": "api",
                    "target": "/api/status",
                    "description": "Verify status API response",
                    "risk_level": "low",
                    "priority": "medium",
                },
            ],
        },
        # Call 2: TestGenerator
        {
            "ui_tests": [
                {
                    "id": "AI-RAW-UI-01",
                    "type": "ui",
                    "title": "AI generated comment submission test",
                    "priority": "high",
                    "steps": [
                        {"action": "goto", "target": "/"},
                        {"action": "fill", "selector": {"strategy": "test_id", "value": "comment-input"}, "value": "AI Verified"},
                    ],
                    "expected": [
                        {"assertion": "page_loaded"},
                        {"assertion": "input_value", "selector": {"strategy": "test_id", "value": "comment-input"}, "expected": "AI Verified"},
                    ],
                }
            ],
            "api_tests": [
                {
                    "id": "AI-RAW-API-01",
                    "type": "api",
                    "title": "AI generated status API check",
                    "priority": "high",
                    "request": {
                        "method": "GET",
                        "path": "/api/status",
                        "timeout_ms": 3000,
                    },
                    "expected": [
                        {"assertion": "status_code", "expected": 200},
                        {"assertion": "content_type", "expected": "application/json"},
                        {"assertion": "json_field_present", "field": "status"},
                        {"assertion": "json_value", "field": "status", "expected": "healthy"},
                    ],
                }
            ],
        },
    ]

    run = await new_run(db)
    run.discovery_enabled = True
    run.testing_enabled = True
    await db.commit()

    pipeline = Pipeline(
        db,
        RunControl(240),
        github=LocalGit(tmp_path / "clones", source),
        ai_provider=mock_ai,
    )
    await pipeline.run(run)

    # 1. Pipeline status must be COMPLETED
    assert run.status == S.COMPLETED, f"Run failed: {run.failure_reason}"

    # 2. Verify persisted TestCase records contain both baseline and AI sources
    all_cases = (
        await db.execute(select(TestCase).where(TestCase.run_id == run.id))
    ).scalars().all()

    baseline_cases = [c for c in all_cases if c.source == "baseline"]
    ai_cases = [c for c in all_cases if c.source == "ai"]

    assert len(baseline_cases) >= 2  # HOME-001, NAV-001, etc.
    assert len(ai_cases) == 2       # AI-UI-001, AI-API-001

    ai_case_ids = {c.definition["id"] for c in ai_cases}
    assert "AI-UI-001" in ai_case_ids
    assert "AI-API-001" in ai_case_ids

    # 3. Verify executed TestResult records: all executed by Phase 3 deterministic executor
    all_results = (
        await db.execute(select(TestResult).where(TestResult.run_id == run.id))
    ).scalars().all()
    assert len(all_results) == len(all_cases)

    case_id_to_def_id = {c.id: c.definition["id"] for c in all_cases}
    results_by_def_id = {case_id_to_def_id[r.test_case_id]: r for r in all_results}

    # Verify AI UI test executed inside container and PASSED
    assert "AI-UI-001" in results_by_def_id
    ai_ui_result = results_by_def_id["AI-UI-001"]
    assert ai_ui_result.status == TestResultStatus.PASS
    assert any(a.get("assertion") == "input_value" and a.get("passed") for a in ai_ui_result.assertions_json)

    # Verify AI API test executed against container loopback and PASSED
    assert "AI-API-001" in results_by_def_id
    ai_api_result = results_by_def_id["AI-API-001"]
    assert ai_api_result.status == TestResultStatus.PASS
    ai_api_passed_ast = {a.get("assertion") for a in ai_api_result.assertions_json if a.get("passed")}
    assert "status_code" in ai_api_passed_ast
    assert "content_type" in ai_api_passed_ast
    assert "json_field_present" in ai_api_passed_ast
    assert "json_value" in ai_api_passed_ast

    # 4. Verify test evidence with test_result_id linkage for AI tests
    ai_evidence = (
        await db.execute(
            select(Evidence).where(Evidence.run_id == run.id, Evidence.test_result_id == ai_ui_result.id)
        )
    ).scalars().all()
    assert len(ai_evidence) >= 1
    for ev in ai_evidence:
        ev_path = evidence_root / ev.path
        assert ev_path.is_file()
        assert ev.size_bytes == ev_path.stat().st_size
        assert hashlib.sha256(ev_path.read_bytes()).hexdigest() == ev.sha256

    # 5. Verify sandbox cleanup: no container leaked
    assert not pipeline.sandbox.client.containers.list(
        all=True, filters={"label": f"testq.run_id={run.id}"}
    )


@pytest.mark.skipif(
    os.environ.get("TESTQ_OLLAMA_TESTS") != "1",
    reason="Requires live local Ollama service (TESTQ_OLLAMA_TESTS=1)",
)
async def test_live_ollama_planner_and_generator():
    """Separately gated test connecting to real local Ollama (if running)."""
    ollama = OllamaProvider()
    if not await ollama.is_available():
        pytest.skip(f"Local Ollama is not active at {ollama.host}")

    from testq_browser.schemas import ApplicationMap, PageRecord, DiscoveryLimits, APIEndpoint

    test_map = ApplicationMap(
        run_id="live-run",
        session_id="live-sess",
        base_url="http://127.0.0.1:3000",
        pages=[PageRecord(url="http://127.0.0.1:3000/", depth=0, title="Live Home")],
        api_endpoints=[APIEndpoint(method="GET", path="/api/health", statuses=[200])],
        limits=DiscoveryLimits(),
    )

    planner = TestPlanner(ollama, max_items=5)
    strategy = await planner.plan(test_map)
    assert len(strategy.items) >= 1

    generator = TestGenerator(ollama, max_tests=5)
    cases = await generator.generate(strategy, test_map, run_id="live-run")
    assert len(cases) >= 1
    assert all(c.definition["id"].startswith("AI-") for c in cases)
