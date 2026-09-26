"""Phase 3 / Hackathon Showcase Deterministic Test Profile.
Real deterministic tests targeting the TestQ demo store application.
These are NOT fake data — they execute against the actual demo app and produce real Playwright/HTTP evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from app.config import settings, APP_ROOT
from app.models.test_case import TestCase
from app.schemas.test_case import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    APITestDefinition,
    APIRequestSpec,
    APIAssertion,
    SelectorSpec,
)

DEMO_REPO_URL = "https://github.com/demo/testq-store"

DEMO_MATCH_URLS = {
    "https://github.com/demo/testq-store",
    "https://github.com/demo/store",
    "https://github.com/demo/juice-shop",
    "demo",
    "testq-demo",
}


def is_demo_repo(url: str | None) -> bool:
    """Return True if the repository URL or identifier refers to the TestQ demo store."""
    if not url:
        return False
    normalized = url.strip().rstrip("/").lower()
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized in DEMO_MATCH_URLS:
        return True
    return "demo/testq" in normalized or "demo/store" in normalized or "/demo" in normalized


def get_demo_source_dir() -> Path:
    """Return absolute path to the local demo application directory."""
    return (APP_ROOT / "demo").resolve()


def create_demo_deterministic_tests(run_id: str) -> list[TestCase]:
    """Create real deterministic tests capable of verifying intentional demo defects:
    - BUG-001: Checkout accepts invalid quantity (0)
    - BUG-002: Login accepts invalid email without format validation
    - BUG-003: Broken cart -> checkout route (/checkout-broken returns 404)
    - Plus passing baseline validation tests
    Labeled clearly with source='demo_deterministic'.
    """
    cases: list[TestCase] = []

    # -----------------------------------------------------------------------
    # BUG-003: Broken cart -> checkout route (UI test)
    # Navigates to /cart and clicks checkout; lands on /checkout-broken -> 404
    # -----------------------------------------------------------------------
    cart_nav_def = UITestDefinition(
        id="DEMO-UI-003",
        type="ui",
        title="[BUG-003] Verify cart proceeds to valid checkout page",
        priority="critical",
        steps=[
            UITestStep(action="goto", target="/cart", timeout_ms=5000),
            UITestStep(
                action="click",
                selector=SelectorSpec(strategy="test_id", value="checkout-nav-btn"),
                timeout_ms=5000,
            ),
        ],
        expected=[
            UIAssertion(assertion="page_loaded"),
            UIAssertion(
                assertion="element_visible",
                selector=SelectorSpec(strategy="test_id", value="place-order-btn"),
            ),
        ],
    )
    cases.append(TestCase(
        run_id=run_id,
        type="ui",
        title=cart_nav_def.title,
        priority=cart_nav_def.priority,
        source="demo_deterministic",
        definition=cart_nav_def.model_dump(mode="json"),
    ))

    # -----------------------------------------------------------------------
    # BUG-001: Checkout rejects invalid quantity 0 (API test)
    # Flawed server allows quantity 0 and confirms order; test expects 400
    # -----------------------------------------------------------------------
    checkout_qty_def = APITestDefinition(
        id="DEMO-API-001",
        type="api",
        title="[BUG-001] Verify checkout rejects zero or negative quantity",
        priority="high",
        request=APIRequestSpec(
            method="POST",
            path="/api/checkout",
            headers={"content-type": "application/json"},
            body={"quantity": 0, "address": "123 AI Boulevard"},
            timeout_ms=5000,
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=400),
        ],
    )
    cases.append(TestCase(
        run_id=run_id,
        type="api",
        title=checkout_qty_def.title,
        priority=checkout_qty_def.priority,
        source="demo_deterministic",
        definition=checkout_qty_def.model_dump(mode="json"),
    ))

    # -----------------------------------------------------------------------
    # BUG-002: Login rejects invalid email format (API test)
    # Flawed server accepts 'bademail' without @ and domain; test expects 400
    # -----------------------------------------------------------------------
    login_email_def = APITestDefinition(
        id="DEMO-API-002",
        type="api",
        title="[BUG-002] Verify login rejects invalid email format",
        priority="high",
        request=APIRequestSpec(
            method="POST",
            path="/api/login",
            headers={"content-type": "application/json"},
            body={"email": "bademail", "password": "password123"},
            timeout_ms=5000,
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=400),
        ],
    )
    cases.append(TestCase(
        run_id=run_id,
        type="api",
        title=login_email_def.title,
        priority=login_email_def.priority,
        source="demo_deterministic",
        definition=login_email_def.model_dump(mode="json"),
    ))

    # -----------------------------------------------------------------------
    # Passing Showcase Test: Products catalog displays items (UI test)
    # Demonstrates that valid functionality passes cleanly
    # -----------------------------------------------------------------------
    products_def = UITestDefinition(
        id="DEMO-UI-004",
        type="ui",
        title="Verify product catalog display and cart buttons",
        priority="medium",
        steps=[
            UITestStep(action="goto", target="/products", timeout_ms=5000),
        ],
        expected=[
            UIAssertion(assertion="page_loaded"),
            UIAssertion(
                assertion="element_visible",
                selector=SelectorSpec(strategy="test_id", value="add-headphones-btn"),
            ),
        ],
    )
    cases.append(TestCase(
        run_id=run_id,
        type="ui",
        title=products_def.title,
        priority=products_def.priority,
        source="demo_deterministic",
        definition=products_def.model_dump(mode="json"),
    ))

    # -----------------------------------------------------------------------
    # Passing Showcase Test: System status endpoint healthy (API test)
    # -----------------------------------------------------------------------
    status_def = APITestDefinition(
        id="DEMO-API-005",
        type="api",
        title="Verify API status endpoint returns healthy version",
        priority="low",
        request=APIRequestSpec(
            method="GET",
            path="/api/status",
            timeout_ms=3000,
        ),
        expected=[
            APIAssertion(assertion="status_code", expected=200),
            APIAssertion(assertion="json_value", field="status", expected="healthy"),
        ],
    )
    cases.append(TestCase(
        run_id=run_id,
        type="api",
        title=status_def.title,
        priority=status_def.priority,
        source="demo_deterministic",
        definition=status_def.model_dump(mode="json"),
    ))

    return cases
