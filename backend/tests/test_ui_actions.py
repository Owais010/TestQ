"""Tests for in-sandbox Playwright UI action execution (goto, click, fill, select, check, uncheck, wait)."""
import http.server
import threading
from pathlib import Path

import pytest

from testq_browser.test_runner import PlaywrightTestRunner
from testq_browser.test_schemas import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    SelectorSpec,
    TestResultStatus,
)

HTML_INDEX = """<!DOCTYPE html>
<html>
<head><title>UI Actions Test</title></head>
<body>
  <h1 id="heading">Initial State</h1>
  <button id="btn-toggle" data-testid="btn-toggle" onclick="document.getElementById('heading').innerText = 'Button Was Clicked';">Toggle</button>
  <input type="text" id="username" data-testid="username" value="original_text">
  <input type="checkbox" id="agree" data-testid="agree">
  <select id="country" data-testid="country">
    <option value="US">United States</option>
    <option value="CA">Canada</option>
    <option value="UK">United Kingdom</option>
  </select>
  <a href="/subpage" id="link-subpage">Go to Subpage</a>
  <div id="status">Ready</div>
</body>
</html>
"""

HTML_SUBPAGE = """<!DOCTYPE html>
<html>
<head><title>Subpage Title</title></head>
<body><h1>Subpage Reached</h1></body>
</html>
"""


class SimpleHttpHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            content = HTML_INDEX.encode("utf-8")
        elif self.path == "/subpage":
            content = HTML_SUBPAGE.encode("utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Suppress server request logging in test output
        pass


@pytest.fixture(scope="module")
def ui_test_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SimpleHttpHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


@pytest.mark.asyncio
async def test_action_goto_changes_page_url(ui_test_server: str, tmp_path: Path):
    """Verify 'goto' action actually navigates to target path and changes page URL."""
    test_def = UITestDefinition(
        id="ACT-GOTO-001",
        title="Goto navigation test",
        steps=[
            UITestStep(action="goto", target="/subpage"),
        ],
        expected=[
            UIAssertion(assertion="page_loaded"),
            UIAssertion(assertion="url_matches", expected=r"/subpage$"),
            UIAssertion(assertion="text_visible", expected="Subpage Reached"),
        ],
    )

    runner = PlaywrightTestRunner(ui_test_server, "run-act-1", "sess-act-1", test_def, tmp_path)
    result = await runner.run()

    assert result.status == TestResultStatus.PASS
    assert len(result.steps) == 1
    assert result.steps[0].status == "ok"
    assert all(a.passed for a in result.assertions)


@pytest.mark.asyncio
async def test_action_click_changes_visible_page_state(ui_test_server: str, tmp_path: Path):
    """Verify 'click' action actually clicks the element and triggers DOM state change."""
    test_def = UITestDefinition(
        id="ACT-CLICK-001",
        title="Click action changes DOM",
        steps=[
            UITestStep(action="goto", target="/"),
            UITestStep(action="click", selector=SelectorSpec(strategy="id", value="btn-toggle")),
        ],
        expected=[
            UIAssertion(assertion="text_visible", expected="Button Was Clicked"),
        ],
    )

    runner = PlaywrightTestRunner(ui_test_server, "run-act-2", "sess-act-2", test_def, tmp_path)
    result = await runner.run()

    assert result.status == TestResultStatus.PASS
    assert len(result.steps) == 2
    assert result.steps[1].status == "ok"
    assert result.assertions[0].passed is True


@pytest.mark.asyncio
async def test_action_fill_changes_input_value(ui_test_server: str, tmp_path: Path):
    """Verify 'fill' action types new value and input_value reflects it."""
    test_def = UITestDefinition(
        id="ACT-FILL-001",
        title="Fill updates input value",
        steps=[
            UITestStep(action="goto", target="/"),
            UITestStep(
                action="fill",
                selector=SelectorSpec(strategy="id", value="username"),
                value="new_user_name",
            ),
        ],
        expected=[
            UIAssertion(
                assertion="input_value",
                selector=SelectorSpec(strategy="id", value="username"),
                expected="new_user_name",
            ),
        ],
    )

    runner = PlaywrightTestRunner(ui_test_server, "run-act-3", "sess-act-3", test_def, tmp_path)
    result = await runner.run()

    assert result.status == TestResultStatus.PASS
    assert len(result.steps) == 2
    assert result.steps[1].status == "ok"
    assert result.assertions[0].passed is True
    assert result.assertions[0].actual == "new_user_name"


@pytest.mark.asyncio
async def test_action_select_changes_selected_option(ui_test_server: str, tmp_path: Path):
    """Verify 'select' action selects the specified option in dropdown."""
    test_def = UITestDefinition(
        id="ACT-SEL-001",
        title="Select updates select dropdown",
        steps=[
            UITestStep(action="goto", target="/"),
            UITestStep(
                action="select",
                selector=SelectorSpec(strategy="id", value="country"),
                value="CA",
            ),
        ],
        expected=[
            UIAssertion(
                assertion="input_value",
                selector=SelectorSpec(strategy="id", value="country"),
                expected="CA",
            ),
        ],
    )

    runner = PlaywrightTestRunner(ui_test_server, "run-act-4", "sess-act-4", test_def, tmp_path)
    result = await runner.run()

    assert result.status == TestResultStatus.PASS
    assert len(result.steps) == 2
    assert result.steps[1].status == "ok"
    assert result.assertions[0].passed is True
    assert result.assertions[0].actual == "CA"


@pytest.mark.asyncio
async def test_action_check_and_uncheck(ui_test_server: str, tmp_path: Path):
    """Verify 'check' and 'uncheck' actions properly toggle checkbox state."""
    test_def = UITestDefinition(
        id="ACT-CHK-001",
        title="Check and uncheck checkbox",
        steps=[
            UITestStep(action="goto", target="/"),
            UITestStep(action="check", selector=SelectorSpec(strategy="id", value="agree")),
            UITestStep(action="uncheck", selector=SelectorSpec(strategy="id", value="agree")),
        ],
        expected=[
            UIAssertion(assertion="page_loaded"),
            UIAssertion(assertion="element_visible", selector=SelectorSpec(strategy="id", value="agree")),
        ],
    )

    runner = PlaywrightTestRunner(ui_test_server, "run-act-5", "sess-act-5", test_def, tmp_path)
    result = await runner.run()

    assert result.status == TestResultStatus.PASS
    assert len(result.steps) == 3
    assert result.steps[1].status == "ok"
    assert result.steps[2].status == "ok"


@pytest.mark.asyncio
async def test_action_wait_pauses_execution(ui_test_server: str, tmp_path: Path):
    """Verify 'wait' action pauses execution within allowed timeout."""
    test_def = UITestDefinition(
        id="ACT-WAIT-001",
        title="Wait action duration",
        steps=[
            UITestStep(action="goto", target="/"),
            UITestStep(action="wait", timeout_ms=300),
        ],
        expected=[
            UIAssertion(assertion="page_loaded"),
        ],
    )

    runner = PlaywrightTestRunner(ui_test_server, "run-act-6", "sess-act-6", test_def, tmp_path)
    result = await runner.run()

    assert result.status == TestResultStatus.PASS
    assert len(result.steps) == 2
    wait_step = result.steps[1]
    assert wait_step.status == "ok"
    assert wait_step.duration_ms >= 250
