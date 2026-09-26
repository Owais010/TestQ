"""
End-to-End Real Docker Integration Test against the Demo Store Application.
Verifies the complete hackathon loop:
Clone -> Build -> Start -> Health -> Discovery -> AI Test Generation -> Deterministic Execution -> Intentional Bug Detection -> AI Failure Analysis -> Persistence -> Cleanup.
Gated by TESTQ_DOCKER_TESTS=1.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.ai.base import AIProvider
from app.config import settings
from app.models.test_case import TestCase, TestResult
from app.models.failure_analysis import FailureAnalysisRecord
from app.models.test_run import TestRunStatus as S
from app.schemas.failure_analysis import FailureAnalysis, FailureSeverity, FailureCategory
from app.worker.pipeline import Pipeline
from tests.test_docker_hardening import LocalGit
from tests.test_hardening import new_run

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("TESTQ_DOCKER_TESTS") != "1", reason="Requires real Docker"
    ),
]


async def test_demo_store_e2e_pipeline(db, tmp_path, monkeypatch):
    """Run the complete pipeline against the real demo application in a real Docker sandbox."""
    demo_src = (Path(__file__).parent.parent.parent / "demo").resolve()
    assert (demo_src / "server.js").exists(), "Demo application must exist"

    # Clone demo to isolated git fixture in tmp_path
    source = tmp_path / "demo_source.git"
    subprocess.run(["git", "clone", str(demo_src), str(source)], check=True, capture_output=True)

    evidence_root = Path(os.environ.get("TESTQ_FIXTURE_EVIDENCE_DIR", str(tmp_path / "evidence"))).resolve()
    monkeypatch.setattr(settings, "evidence_dir", evidence_root)

    # Mock AI provider: generates a targeted test on the broken cart checkout link,
    # and analyzes the failure when it occurs
    mock_ai = AsyncMock(spec=AIProvider)
    mock_ai.generate.side_effect = [
        # Call 1: TestPlanner strategy
        {
            "summary": "AI strategy targeting checkout flow and cart navigation",
            "items": [
                {
                    "id": "STRAT-001",
                    "category": "navigation",
                    "target": "/cart",
                    "description": "Traverse cart checkout link to verify checkout accessibility",
                    "risk_level": "high",
                    "priority": "high",
                }
            ],
        },

        # Call 2: TestGenerator structured test cases
        {
            "ui_tests": [
                {
                    "id": "AI-UI-DEMO-01",
                    "type": "ui",
                    "title": "Verify cart proceeds to valid checkout page",
                    "priority": "high",
                    "steps": [
                        {"action": "goto", "target": "/cart"},
                        {"action": "click", "selector": {"strategy": "test_id", "value": "checkout-nav-btn"}},
                    ],
                    "expected": [
                        {"assertion": "page_loaded"},
                        {"assertion": "element_visible", "selector": {"strategy": "test_id", "value": "place-order-btn"}},
                    ],

                }
            ],
            "api_tests": [],
        },
        # Call 3: Failure Analyzer
        FailureAnalysis(
            title="Broken Navigation: Cart Proceeds to 404 Route",
            severity=FailureSeverity.CRITICAL,
            category=FailureCategory.NAVIGATION,
            summary="Clicking Proceed to Checkout navigated to /checkout-broken which resulted in a 404 error instead of the checkout page.",
            likely_root_cause="The cart checkout anchor tag contains an incorrect href attribute '/checkout-broken'.",
            reproduction_steps=[
                "Navigate to /cart",
                "Click the 'Proceed to Checkout' button",
                "Observe navigation to non-existent route /checkout-broken",
            ],
            evidence_references=["cart_checkout_nav.png"],
            confidence=0.96,
        ),
    ]

    run = await new_run(db)
    run.discovery_enabled = True
    run.testing_enabled = True
    await db.commit()

    pipeline = Pipeline(
        db,
        github=LocalGit(tmp_path / "clones", source),
        ai_provider=mock_ai,
    )
    await pipeline.run(run)


    await db.refresh(run)

    # Assertions
    assert run.status == S.COMPLETED
    assert run.progress.get("testing") == "completed"
    assert run.progress.get("analyzing_failures") == "completed"

    # Verify test cases were persisted (baseline + AI)
    cases = (await db.execute(
        select(TestCase).where(TestCase.run_id == run.id).order_by(TestCase.created_at)
    )).scalars().all()
    assert len(cases) >= 2  # Baseline HOME-001 + AI test
    ai_cases = [c for c in cases if c.source == "ai"]
    assert len(ai_cases) == 1
    assert ai_cases[0].title == "Verify cart proceeds to valid checkout page"

    # Verify execution results contain at least one failure on the broken link
    results = (await db.execute(
        select(TestResult).where(TestResult.run_id == run.id)
    )).scalars().all()
    assert len(results) == len(cases)

    failed_results = [r for r in results if r.status != "PASS"]
    assert len(failed_results) >= 1, "The broken navigation test must fail"

    # Verify FailureAnalysisRecord was generated and persisted
    fa_records = (await db.execute(
        select(FailureAnalysisRecord).where(FailureAnalysisRecord.run_id == run.id)
    )).scalars().all()

    assert len(fa_records) >= 1
    defect = fa_records[0]
    assert defect.severity == "critical"
    assert defect.category == "navigation"
    assert defect.title == "Broken Navigation: Cart Proceeds to 404 Route"
    assert defect.confidence == 0.96
    assert len(defect.reproduction_steps) == 3

    # Verify container cleanup
    assert run.container_id is None
