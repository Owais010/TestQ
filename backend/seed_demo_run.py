"""Seed the TestQ database with authentic completed demo run data for hackathon presentation."""
import asyncio
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure backend package is in path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select, delete
from app.database import async_session, init_db
from app.models.project import Project
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.discovery import DiscoverySession, Evidence
from app.models.test_case import TestCase, TestResult
from app.models.failure_analysis import FailureAnalysisRecord
from app.models.log import Log

from testq_browser.schemas import (
    ApplicationMap, PageRecord, Link, Element, SelectorCandidate,
    Form, APIEndpoint, Artifact, NetworkRequest, DiscoveryLimits
)


async def seed():
    await init_db()
    async with async_session() as db:
        repo_url = "https://github.com/demo/juice-shop"
        existing_project = (await db.execute(select(Project).where(Project.repository_url == repo_url))).scalar_one_or_none()
        if not existing_project:
            project = Project(
                repository_url=repo_url,
                default_branch="main",
            )
            db.add(project)
            await db.flush()
        else:
            project = existing_project

        run_id = "demo-run-juice-shop"
        # If run exists, delete it so we can re-seed cleanly
        existing_run = await db.get(TestRun, run_id)
        if existing_run:
            # Delete child records
            await db.execute(delete(FailureAnalysisRecord).where(FailureAnalysisRecord.run_id == run_id))
            await db.execute(delete(Evidence).where(Evidence.run_id == run_id))
            await db.execute(delete(TestResult).where(TestResult.run_id == run_id))
            await db.execute(delete(TestCase).where(TestCase.run_id == run_id))
            await db.execute(delete(DiscoverySession).where(DiscoverySession.run_id == run_id))
            await db.execute(delete(Log).where(Log.run_id == run_id))
            await db.delete(existing_run)
            await db.flush()

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=4, seconds=35)
        finish_time = now - timedelta(seconds=15)

        run = TestRun(
            id=run_id,
            project_id=project.id,
            branch="main",
            commit_sha="e8f492a3b1d",
            status=S.COMPLETED,
            failure_reason=None,
            failure_stage=None,
            cancellation_requested=False,
            discovery_enabled=True,
            testing_enabled=True,
            detected_config={
                "project_type": "Node.js (Express)",
                "framework": "express",
                "package_manager": "npm",
                "port": 3000,
                "routes_detected": 4,
                "docker_base_image": "node:18-alpine"
            },
            progress={
                "cloning": "completed",
                "analyzing": "completed",
                "building": "completed",
                "starting": "completed",
                "ready": "completed",
                "discovering": "completed",
                "discovery_complete": "completed",
                "testing": "completed",
                "analyzing_failures": "completed",
                "report": "completed"
            },
            total_tests=3,
            passed_tests=2,
            failed_tests=1,
            container_id="c1a84f32e909",
            sandbox_port=4321,
            started_at=start_time,
            finished_at=finish_time,
            created_at=start_time - timedelta(seconds=5),
        )
        db.add(run)
        await db.flush()

        # Build typed ApplicationMap
        disc_session_id = "disc-sess-001"
        base_url = "http://127.0.0.1:4321"

        page_home = PageRecord(
            url=f"{base_url}/",
            final_url=f"{base_url}/",
            depth=0,
            title="Modern Demo Store — Autonomous Showcase",
            timestamp=start_time + timedelta(seconds=45),
            navigation="ok",
            status=200,
            screenshot="homepage.png",
            links=[
                Link(href="/catalog", text="Catalog", source_page=f"{base_url}/", internal=True),
                Link(href="/cart", text="Cart", source_page=f"{base_url}/", internal=True),
            ],
            buttons=[
                Element(
                    tag="a",
                    text="Explore Catalog",
                    element_id="cta-catalog",
                    selectors=[SelectorCandidate(strategy="id", value="cta-catalog")]
                ),
                Element(
                    tag="a",
                    text="View Cart",
                    element_id="nav-cart",
                    selectors=[SelectorCandidate(strategy="id", value="nav-cart")]
                )
            ]
        )

        page_catalog = PageRecord(
            url=f"{base_url}/catalog",
            final_url=f"{base_url}/catalog",
            depth=1,
            title="Product Catalog — TestQ Store",
            timestamp=start_time + timedelta(seconds=55),
            navigation="ok",
            status=200,
            screenshot="homepage.png",
            links=[
                Link(href="/products/1", text="Quantum Keyboard", source_page=f"{base_url}/catalog", internal=True),
                Link(href="/cart", text="Cart", source_page=f"{base_url}/catalog", internal=True),
            ],
            buttons=[
                Element(
                    tag="button",
                    text="Add to Cart",
                    element_id="btn-add-item",
                    selectors=[SelectorCandidate(strategy="id", value="btn-add-item")]
                )
            ],
            inputs=[
                Element(
                    tag="input",
                    name="search",
                    placeholder="Search inventory...",
                    input_type="text",
                    element_id="catalog-search",
                    selectors=[SelectorCandidate(strategy="id", value="catalog-search")]
                )
            ]
        )

        page_cart = PageRecord(
            url=f"{base_url}/cart",
            final_url=f"{base_url}/cart",
            depth=1,
            title="Shopping Cart — Checkout Required",
            timestamp=start_time + timedelta(seconds=65),
            navigation="ok",
            status=200,
            screenshot="homepage.png",
            links=[
                Link(href="/catalog", text="Catalog", source_page=f"{base_url}/cart", internal=True),
            ],
            buttons=[
                Element(
                    tag="button",
                    text="Proceed to Checkout",
                    element_id="btn-checkout",
                    selectors=[SelectorCandidate(strategy="id", value="btn-checkout")]
                )
            ],
            forms=[
                Form(
                    identifier="cart-checkout-form",
                    action="/api/checkout",
                    method="POST",
                    controls=[
                        Element(
                            tag="input",
                            name="discount_code",
                            placeholder="PROMO2026",
                            input_type="text",
                            element_id="discount",
                            selectors=[SelectorCandidate(strategy="id", value="discount")]
                        )
                    ],
                    buttons=[
                        Element(
                            tag="button",
                            text="Proceed to Checkout",
                            element_id="btn-checkout",
                            selectors=[SelectorCandidate(strategy="id", value="btn-checkout")]
                        )
                    ]
                )
            ]
        )

        page_product = PageRecord(
            url=f"{base_url}/products/1",
            final_url=f"{base_url}/products/1",
            depth=2,
            title="Quantum Mechanical Keyboard — TestQ Store",
            timestamp=start_time + timedelta(seconds=70),
            navigation="ok",
            status=200,
            screenshot="homepage.png",
            links=[
                Link(href="/catalog", text="Catalog", source_page=f"{base_url}/products/1", internal=True),
            ],
            buttons=[
                Element(
                    tag="button",
                    text="Add to Cart",
                    element_id="btn-buy",
                    selectors=[SelectorCandidate(strategy="id", value="btn-buy")]
                )
            ],
            inputs=[
                Element(
                    tag="input",
                    name="quantity",
                    input_type="number",
                    element_id="qty",
                    selectors=[SelectorCandidate(strategy="id", value="qty")]
                )
            ]
        )

        app_map = ApplicationMap(
            schema_version=1,
            run_id=run.id,
            session_id=disc_session_id,
            base_url=base_url,
            status="completed",
            started_at=start_time + timedelta(seconds=40),
            finished_at=start_time + timedelta(seconds=75),
            pages=[page_home, page_catalog, page_cart, page_product],
            api_endpoints=[
                APIEndpoint(method="GET", path="/api/items", statuses=[200]),
                APIEndpoint(method="POST", path="/api/cart/add", statuses=[200]),
                APIEndpoint(method="POST", path="/api/checkout", statuses=[404]),
            ],
            requests=[
                NetworkRequest(
                    page_url=f"{base_url}/",
                    method="GET",
                    url=f"{base_url}/",
                    path="/",
                    resource_type="document",
                    status=200,
                    duration_ms=12.4,
                    internal=True
                )
            ],
            artifacts=[
                Artifact(
                    kind="screenshot",
                    filename="homepage.png",
                    page_url=f"{base_url}/",
                    size_bytes=8198,
                    sha256="ba762b157f7bdd222a1376de22ce92b391197cb6bbbc15f15465349eb7e260cd",
                    media_type="image/png"
                )
            ],
            limits=DiscoveryLimits(max_pages=12, max_depth=3)
        )

        discovery = DiscoverySession(
            id=disc_session_id,
            run_id=run.id,
            status="completed",
            application_map=app_map.model_dump(mode="json"),
            started_at=start_time + timedelta(seconds=40),
            finished_at=start_time + timedelta(seconds=75),
        )
        db.add(discovery)
        await db.flush()

        # Test Cases
        tc_home = TestCase(
            id="HOME-001",
            run_id=run.id,
            type="ui",
            title="Baseline: Homepage Navigation & Critical Elements",
            priority="high",
            source="baseline",
            definition={
                "steps": [
                    {"action": "navigate", "url": "/"},
                    {"action": "assert_status", "status": 200},
                    {"action": "assert_visible", "selector": "a#cta-catalog"}
                ]
            }
        )
        tc_nav = TestCase(
            id="NAV-001",
            run_id=run.id,
            type="ui",
            title="Baseline: Catalog Route & Interactive Search Input",
            priority="medium",
            source="baseline",
            definition={
                "steps": [
                    {"action": "navigate", "url": "/catalog"},
                    {"action": "assert_status", "status": 200},
                    {"action": "type", "selector": "input#catalog-search", "text": "keyboard"},
                    {"action": "assert_visible", "selector": "button.btn-add-item"}
                ]
            }
        )
        tc_ai_cart = TestCase(
            id="AI-CART-001",
            run_id=run.id,
            type="ui",
            title="AI Generated: Cart Checkout Flow & Backend State Mutation",
            priority="critical",
            source="ai",
            definition={
                "steps": [
                    {"action": "navigate", "url": "/"},
                    {"action": "click", "selector": "a#cta-catalog"},
                    {"action": "click", "selector": "button.btn-add-item"},
                    {"action": "navigate", "url": "/cart"},
                    {"action": "click", "selector": "button#btn-checkout"},
                    {"action": "assert_status", "expected": 200}
                ]
            }
        )
        db.add_all([tc_home, tc_nav, tc_ai_cart])
        await db.flush()

        # Test Results
        tr_home = TestResult(
            id="RES-HOME-001",
            test_case_id=tc_home.id,
            run_id=run.id,
            status="PASS",
            started_at=start_time + timedelta(seconds=110),
            finished_at=start_time + timedelta(seconds=111),
            duration_ms=242.0,
            expected={"status": 200, "visible": "a#cta-catalog"},
            actual={"status": 200, "visible": True},
            error=None
        )
        tr_nav = TestResult(
            id="RES-NAV-001",
            test_case_id=tc_nav.id,
            run_id=run.id,
            status="PASS",
            started_at=start_time + timedelta(seconds=112),
            finished_at=start_time + timedelta(seconds=113),
            duration_ms=315.0,
            expected={"status": 200, "text_input": "keyboard"},
            actual={"status": 200, "text_input": "keyboard"},
            error=None
        )
        tr_ai_cart = TestResult(
            id="RES-AI-CART-001",
            test_case_id=tc_ai_cart.id,
            run_id=run.id,
            status="FAIL",
            started_at=start_time + timedelta(seconds=114),
            finished_at=start_time + timedelta(seconds=117),
            duration_ms=640.0,
            expected={"status": 200, "endpoint": "/api/checkout"},
            actual={"status": 404, "body": "Cannot POST /api/checkout"},
            error="AssertionError: Expected HTTP 200 on POST /api/checkout, received HTTP 404 Not Found"
        )
        db.add_all([tr_home, tr_nav, tr_ai_cart])
        await db.flush()

        # Failure Analysis
        fa = FailureAnalysisRecord(
            id="FA-CART-001",
            run_id=run.id,
            test_result_id=tr_ai_cart.id,
            test_case_id=tc_ai_cart.id,
            title="Unhandled 404 Endpoint on Autonomous Checkout Flow",
            severity="HIGH",
            category="FUNCTIONAL",
            summary="Deterministic execution triggered a fatal HTTP 404 Not Found when submitting cart items through the checkout button.",
            likely_root_cause="The Express router in server.js does not register the POST '/api/checkout' endpoint. When button#btn-checkout initiates a fetch to /api/checkout, the Express application falls back to default 404 handler (Cannot POST /api/checkout).",
            reproduction_steps=[
                "1. Navigate to http://127.0.0.1:4321/",
                "2. Click 'Explore Catalog' (a#cta-catalog)",
                "3. Click 'Add to Cart' (button.btn-add-item)",
                "4. Navigate to /cart",
                "5. Click 'Proceed to Checkout' (button#btn-checkout)",
                "6. Observe network inspector: POST /api/checkout returns 404 Not Found"
            ],
            evidence_references=["homepage.png", "trace-000.zip"],
            confidence=0.96,
            created_at=start_time + timedelta(seconds=125),
        )
        db.add(fa)

        # Evidence records
        ev1 = Evidence(
            id="EV-001",
            run_id=run.id,
            session_id=discovery.id,
            test_result_id=tr_home.id,
            page_url="http://127.0.0.1:4321/",
            kind="screenshot",
            path=f"evidence/{run.id}/discovery/{discovery.id}/homepage.png",
            size_bytes=8198,
            sha256="ba762b157f7bdd222a1376de22ce92b391197cb6bbbc15f15465349eb7e260cd",
            media_type="image/png"
        )
        ev2 = Evidence(
            id="EV-002",
            run_id=run.id,
            session_id=discovery.id,
            test_result_id=tr_ai_cart.id,
            page_url="http://127.0.0.1:4321/cart",
            kind="trace",
            path=f"evidence/{run.id}/discovery/{discovery.id}/trace-000.zip",
            size_bytes=669,
            sha256="db2205f607186b7168b64efb087620852e2576a99892aa040a4ee3a5c14c5c7b",
            media_type="application/zip"
        )
        db.add_all([ev1, ev2])

        strategy_payload = {
            "run_id": run.id,
            "summary": "AI Adversarial Strategy: 8 high-risk attack vectors synthesized from dynamic Playwright crawl",
            "items": [
                {
                    "id": "STRAT-NAV-001",
                    "category": "Navigation",
                    "target": "/catalog -> /cart",
                    "description": "Cart state persistence and route transition integrity across client-side router transitions.",
                    "risk_level": "critical",
                    "priority": "critical"
                },
                {
                    "id": "STRAT-AUTH-002",
                    "category": "Authentication",
                    "target": "/login & /api/auth",
                    "description": "Session token verification, CSRF header enforcement, and unauthenticated redirect boundaries.",
                    "risk_level": "high",
                    "priority": "high"
                },
                {
                    "id": "STRAT-VAL-003",
                    "category": "Validation",
                    "target": "form#payment-form",
                    "description": "Strict payment payload validation, Luhn algorithm check, and numeric sanitizer boundaries.",
                    "risk_level": "high",
                    "priority": "high"
                },
                {
                    "id": "STRAT-INP-004",
                    "category": "Inputs",
                    "target": "input#catalog-search",
                    "description": "Adversarial character injection, Unicode fuzzing, and query parameter DOM-XSS resistance.",
                    "risk_level": "medium",
                    "priority": "medium"
                },
                {
                    "id": "STRAT-BND-005",
                    "category": "Boundary",
                    "target": "input#item-quantity",
                    "description": "Negative integer quantities, float payloads, and overflow inventory boundary checks.",
                    "risk_level": "medium",
                    "priority": "medium"
                },
                {
                    "id": "STRAT-API-006",
                    "category": "API",
                    "target": "POST /api/checkout",
                    "description": "Contract conformity on JSON payload, HTTP status semantics, and router registration verification.",
                    "risk_level": "critical",
                    "priority": "critical"
                },
                {
                    "id": "STRAT-WRK-007",
                    "category": "Workflow",
                    "target": "Catalog -> Cart -> Checkout",
                    "description": "Multi-step transactional user workflow across local state storage and backend mutation endpoints.",
                    "risk_level": "critical",
                    "priority": "critical"
                },
                {
                    "id": "STRAT-ERR-008",
                    "category": "Error Handling",
                    "target": "/non-existent-route & 404 boundaries",
                    "description": "Graceful React error boundary rendering and zero stack-trace leakage on unhandled routes.",
                    "risk_level": "medium",
                    "priority": "medium"
                }
            ],
            "total": 8
        }
        log_entries = [
            ("system", "INFO", "TestQ autonomous QA runner initialized with zero-trust container policy"),
            ("cloning", "INFO", "Cloned https://github.com/demo/juice-shop branch main at commit e8f492a3b1d"),
            ("analyzing", "INFO", "Detected Node.js Express application on port 3000 with 4 static routes"),
            ("building", "INFO", "Building isolated Docker container image testq-sandbox:e8f492a"),
            ("starting", "INFO", "Sandbox container c1a84f32e909 launched with 2.0 CPU / 2GB RAM limits and non-root user"),
            ("ready", "INFO", "Container health check passed: http://127.0.0.1:4321/ is healthy"),
            ("discovering", "INFO", "Playwright discovery spider initiated: max_pages=12, max_depth=3"),
            ("discovering", "INFO", "Discovered 4 pages and 3 API endpoints. Application map generated and validated"),
            ("ai_strategy", "INFO", json.dumps(strategy_payload)),
            ("testing", "INFO", "Deterministic Test Executor starting: 2 baseline tests, 1 AI-generated test"),
            ("testing", "INFO", "[PASS] HOME-001: Baseline Homepage Navigation (242ms)"),
            ("testing", "INFO", "[PASS] NAV-001: Baseline Catalog Route (315ms)"),
            ("testing", "ERROR", "[FAIL] AI-CART-001: AssertionError: Expected HTTP 200 on POST /api/checkout, received HTTP 404 Not Found"),
            ("analyzing_failures", "INFO", "Triggering AI Failure Analyzer for RES-AI-CART-001 with factual execution traces"),
            ("analyzing_failures", "INFO", "AI Failure Analysis complete: High severity defect identified in server.js router table (confidence: 96%)"),
            ("system", "INFO", "Sandbox container c1a84f32e909 stopped and cleaned up with 0 orphaned resources"),
            ("system", "INFO", "Test run demo-run-juice-shop completed successfully")
        ]

        for idx, (src, lvl, msg) in enumerate(log_entries):
            entry = Log(
                run_id=run.id,
                source=src,
                level=lvl,
                message=msg,
                timestamp=start_time + timedelta(seconds=idx * 7)
            )
            db.add(entry)

        await db.commit()
        print(f"Successfully re-seeded typed demo run {run.id} into testq.db!")


if __name__ == "__main__":
    asyncio.run(seed())
