"""Tests for Phase 4 AI Test Generator."""
import pytest
from unittest.mock import AsyncMock

from app.ai.base import (
    AIProvider,
    AIError,
    AIUnavailableError,
    AISchemaValidationError,
)
from app.models.test_case import TestCase
from app.schemas.ai_test import TestStrategy, TestStrategyItem
from app.services.test_generator import TestGenerator, GENERATOR_SYSTEM_PROMPT
from testq_browser.schemas import ApplicationMap, PageRecord, DiscoveryLimits, Element, SelectorCandidate, APIEndpoint


@pytest.fixture
def sample_strategy():
    return TestStrategy(
        summary="Strategic test targets",
        items=[
            TestStrategyItem(
                id="STRAT-001",
                category="navigation",
                target="/dashboard",
                description="Verify dashboard route",
                risk_level="medium",
                priority="high",
            ),
            TestStrategyItem(
                id="STRAT-002",
                category="api",
                target="/api/items",
                description="Verify items API",
                risk_level="high",
                priority="critical",
            ),
        ],
    )


@pytest.fixture
def sample_app_map():
    return ApplicationMap(
        run_id="run-1",
        session_id="sess-1",
        base_url="http://127.0.0.1:3000",
        pages=[
            PageRecord(
                url="http://127.0.0.1:3000/dashboard",
                depth=1,
                title="Dashboard",
                buttons=[
                    Element(
                        tag="button",
                        text="Refresh",
                        element_id="refresh-btn",
                        selectors=[SelectorCandidate(strategy="id", value="refresh-btn")],
                    )
                ],
                inputs=[
                    Element(
                        tag="input",
                        input_type="text",
                        name="search",
                        selectors=[SelectorCandidate(strategy="name", value="search")],
                    )
                ],
            )
        ],
        api_endpoints=[
            APIEndpoint(method="GET", path="/api/items", statuses=[200])
        ],
        limits=DiscoveryLimits(),
    )


@pytest.mark.asyncio
async def test_generator_generates_valid_ui_and_api_tests(sample_strategy, sample_app_map):
    mock_provider = AsyncMock(spec=AIProvider)
    mock_provider.generate.return_value = {
        "ui_tests": [
            {
                "id": "AI-RAW-001",
                "type": "ui",
                "title": "Search input on dashboard",
                "priority": "high",
                "steps": [
                    {"action": "goto", "target": "/dashboard"},
                    {"action": "fill", "selector": {"strategy": "name", "value": "search"}, "value": "widget"},
                    {"action": "click", "selector": {"strategy": "id", "value": "refresh-btn"}},
                ],
                "expected": [
                    {"assertion": "page_loaded"},
                    {"assertion": "input_value", "selector": {"strategy": "name", "value": "search"}, "expected": "widget"},
                ],
            }
        ],
        "api_tests": [
            {
                "id": "AI-RAW-002",
                "type": "api",
                "title": "Query items API",
                "priority": "critical",
                "request": {
                    "method": "GET",
                    "path": "/api/items",
                    "timeout_ms": 3000,
                },
                "expected": [
                    {"assertion": "status_code", "expected": 200},
                    {"assertion": "content_type", "expected": "application/json"},
                ],
            }
        ],
    }

    generator = TestGenerator(mock_provider)
    cases = await generator.generate(sample_strategy, sample_app_map, run_id="run-1")

    assert len(cases) == 2
    assert cases[0].type == "ui"
    assert cases[0].source == "ai"
    assert cases[0].definition["id"] == "AI-UI-001"
    assert cases[0].title == "Search input on dashboard"

    assert cases[1].type == "api"
    assert cases[1].source == "ai"
    assert cases[1].definition["id"] == "AI-API-001"
    assert cases[1].title == "Query items API"

    # Verify generator system prompt was passed
    call_args = mock_provider.generate.call_args
    assert call_args.kwargs["system_prompt"] == GENERATOR_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_generator_rejects_unsupported_actions(sample_strategy, sample_app_map):
    mock_provider = AsyncMock(spec=AIProvider)
    # The model attempts an unsupported action "eval" and "hover"
    mock_provider.generate.return_value = {
        "ui_tests": [
            {
                "id": "AI-INVALID-001",
                "type": "ui",
                "title": "Malicious eval test",
                "priority": "critical",
                "steps": [
                    {"action": "eval", "target": "window.alert(1)"},
                ],
                "expected": [{"assertion": "page_loaded"}],
            },
            {
                "id": "AI-VALID-001",
                "type": "ui",
                "title": "Valid navigation test",
                "priority": "medium",
                "steps": [
                    {"action": "goto", "target": "/dashboard"},
                ],
                "expected": [{"assertion": "page_loaded"}],
            },
        ],
        "api_tests": [],
    }

    generator = TestGenerator(mock_provider)
    cases = await generator.generate(sample_strategy, sample_app_map, run_id="run-1")

    # Only the valid test must survive; eval test is rejected
    assert len(cases) == 1
    assert cases[0].definition["id"] == "AI-UI-001"
    assert cases[0].title == "Valid navigation test"


@pytest.mark.asyncio
async def test_generator_rejects_external_urls(sample_strategy, sample_app_map):
    mock_provider = AsyncMock(spec=AIProvider)
    mock_provider.generate.return_value = {
        "ui_tests": [
            {
                "id": "AI-EXT-001",
                "type": "ui",
                "title": "External navigation attempt",
                "priority": "high",
                "steps": [
                    {"action": "goto", "target": "https://evil.example.com/exploit"},
                ],
                "expected": [{"assertion": "page_loaded"}],
            }
        ],
        "api_tests": [
            {
                "id": "AI-EXT-002",
                "type": "api",
                "title": "External API request attempt",
                "priority": "high",
                "request": {
                    "method": "GET",
                    "path": "https://evil.example.com/api/steal",
                },
                "expected": [{"assertion": "status_code", "expected": 200}],
            }
        ],
    }

    generator = TestGenerator(mock_provider)
    # Both external attempts must be rejected with AISchemaValidationError (not silently returning [])
    with pytest.raises(AISchemaValidationError):
        await generator.generate(sample_strategy, sample_app_map, run_id="run-1")


@pytest.mark.asyncio
async def test_generator_deduplication_against_baseline(sample_strategy, sample_app_map):
    """Verify that AI-generated tests equivalent to baseline tests are deterministically dropped."""
    # Baseline test already tests navigating to /dashboard
    baseline_case = TestCase(
        run_id="run-1",
        type="ui",
        title="Internal route /dashboard loads",
        priority="high",
        source="baseline",
        definition={
            "id": "NAV-001",
            "type": "ui",
            "title": "Internal route /dashboard loads",
            "priority": "high",
            "steps": [{"action": "goto", "target": "/dashboard"}],
            "expected": [{"assertion": "page_loaded"}],
        },
    )

    mock_provider = AsyncMock(spec=AIProvider)
    mock_provider.generate.return_value = {
        "ui_tests": [
            # Duplicate of baseline: same steps and expected
            {
                "id": "AI-DUP-001",
                "type": "ui",
                "title": "Duplicate dashboard check",
                "priority": "medium",
                "steps": [{"action": "goto", "target": "/dashboard"}],
                "expected": [{"assertion": "page_loaded"}],
            },
            # Non-duplicate: tests button interaction
            {
                "id": "AI-NEW-001",
                "type": "ui",
                "title": "Click refresh on dashboard",
                "priority": "high",
                "steps": [
                    {"action": "goto", "target": "/dashboard"},
                    {"action": "click", "selector": {"strategy": "id", "value": "refresh-btn"}},
                ],
                "expected": [{"assertion": "page_loaded"}],
            },
        ],
        "api_tests": [],
    }

    generator = TestGenerator(mock_provider)
    cases = await generator.generate(
        sample_strategy, sample_app_map, run_id="run-1", baseline_cases=[baseline_case]
    )

    assert len(cases) == 1
    assert cases[0].title == "Click refresh on dashboard"
    assert cases[0].definition["id"] == "AI-UI-001"


@pytest.mark.asyncio
async def test_generator_deduplication_among_ai_tests(sample_strategy, sample_app_map):
    """Verify that multiple equivalent AI-generated tests are deduplicated to 1."""
    mock_provider = AsyncMock(spec=AIProvider)
    mock_provider.generate.return_value = {
        "ui_tests": [
            {
                "id": "AI-1",
                "type": "ui",
                "title": "First dashboard test",
                "priority": "medium",
                "steps": [{"action": "goto", "target": "/dashboard"}],
                "expected": [{"assertion": "page_loaded"}],
            },
            {
                "id": "AI-2",
                "type": "ui",
                "title": "Duplicate wording same test",
                "priority": "low",
                "steps": [{"action": "goto", "target": "/dashboard"}],
                "expected": [{"assertion": "page_loaded"}],
            },
        ],
        "api_tests": [],
    }

    generator = TestGenerator(mock_provider)
    cases = await generator.generate(sample_strategy, sample_app_map, run_id="run-1")

    assert len(cases) == 1
    assert cases[0].definition["id"] == "AI-UI-001"


@pytest.mark.asyncio
async def test_generator_enforces_max_tests_limit(sample_strategy, sample_app_map):
    mock_provider = AsyncMock(spec=AIProvider)
    mock_provider.generate.return_value = {
        "ui_tests": [
            {
                "id": f"AI-TEST-{i}",
                "type": "ui",
                "title": f"Test {i}",
                "priority": "low",
                "steps": [
                    {"action": "goto", "target": f"/dashboard"},
                    {"action": "wait", "timeout_ms": 100 * i},
                ],
                "expected": [{"assertion": "page_loaded"}],
            }
            for i in range(1, 15)
        ],
        "api_tests": [],
    }

    generator = TestGenerator(mock_provider, max_tests=4)
    cases = await generator.generate(sample_strategy, sample_app_map, run_id="run-1")

    assert len(cases) == 4
    assert cases[-1].definition["id"] == "AI-UI-004"


@pytest.mark.asyncio
async def test_generator_retries_on_malformed_output(sample_strategy, sample_app_map):
    mock_provider = AsyncMock(spec=AIProvider)
    mock_provider.generate.side_effect = [
        AISchemaValidationError("Invalid JSON schema"),
        {
            "ui_tests": [
                {
                    "id": "AI-RETRY-001",
                    "type": "ui",
                    "title": "Recovered test",
                    "priority": "high",
                    "steps": [{"action": "goto", "target": "/dashboard"}],
                    "expected": [{"assertion": "page_loaded"}],
                }
            ],
            "api_tests": [],
        },
    ]

    generator = TestGenerator(mock_provider, max_retries=1)
    cases = await generator.generate(sample_strategy, sample_app_map, run_id="run-1")

    assert mock_provider.generate.call_count == 2
    assert len(cases) == 1
    assert cases[0].title == "Recovered test"
