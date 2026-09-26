"""Tests for deterministic selector resolution in in-sandbox test runner."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.test_case import SelectorSpec, UITestStep
from testq_browser.test_runner import resolve_unique_locator


class MockLocator:
    def __init__(self, count_val):
        self.count_val = count_val

    async def count(self):
        return self.count_val


@pytest.mark.asyncio
async def test_resolve_unique_first_candidate():
    page = MagicMock()
    # Mock test_id match 1
    mock_loc = MockLocator(1)
    page.get_by_test_id = MagicMock(return_value=mock_loc)

    step = UITestStep(
        action="click",
        candidates=[
            SelectorSpec(strategy="test_id", value="submit-btn"),
            SelectorSpec(strategy="id", value="submit"),
        ],
    )

    resolved = await resolve_unique_locator(page, step)
    assert resolved == mock_loc
    page.get_by_test_id.assert_called_once_with("submit-btn")


@pytest.mark.asyncio
async def test_resolve_fallback_candidate():
    page = MagicMock()
    # test_id returns 0 matches
    page.get_by_test_id = MagicMock(return_value=MockLocator(0))
    # id returns 1 match
    id_loc = MockLocator(1)
    page.locator = MagicMock(return_value=id_loc)

    step = UITestStep(
        action="click",
        candidates=[
            SelectorSpec(strategy="test_id", value="nonexistent-btn"),
            SelectorSpec(strategy="id", value="real-btn"),
        ],
    )

    resolved = await resolve_unique_locator(page, step)
    assert resolved == id_loc
    page.locator.assert_called_once_with("#real-btn")


@pytest.mark.asyncio
async def test_resolve_no_match_raises_error():
    page = MagicMock()
    page.get_by_test_id = MagicMock(return_value=MockLocator(0))
    page.locator = MagicMock(return_value=MockLocator(0))

    step = UITestStep(
        action="click",
        candidates=[
            SelectorSpec(strategy="test_id", value="ghost-btn"),
            SelectorSpec(strategy="css", value=".ghost"),
        ],
    )

    with pytest.raises(ValueError) as exc:
        await resolve_unique_locator(page, step)
    assert "Element not found" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_ambiguous_match_raises_error():
    page = MagicMock()
    # css selector matches 3 elements
    page.locator = MagicMock(return_value=MockLocator(3))

    step = UITestStep(
        action="click",
        candidates=[
            SelectorSpec(strategy="css", value="button"),
        ],
    )

    with pytest.raises(ValueError) as exc:
        await resolve_unique_locator(page, step)
    assert "Ambiguous selector match" in str(exc.value)
    assert "3 matching elements" in str(exc.value)


@pytest.mark.asyncio
async def test_role_strategy_resolution():
    page = MagicMock()
    role_loc = MockLocator(1)
    page.get_by_role = MagicMock(return_value=role_loc)

    step = UITestStep(
        action="click",
        selector=SelectorSpec(strategy="role", value="Save Changes", role="button", exact=True),
    )

    resolved = await resolve_unique_locator(page, step)
    assert resolved == role_loc
    page.get_by_role.assert_called_once_with("button", name="Save Changes", exact=True)
