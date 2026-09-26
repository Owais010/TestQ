"""Dedicated tests for all 7 deterministic UI assertions:
page_loaded, url_matches, text_visible, element_visible, element_hidden, input_value, http_status.
Each assertion is tested for both PASS and FAIL outcomes (yielding TestResultStatus.FAIL).
"""
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

HTML_ASSERTIONS = """<!DOCTYPE html>
<html>
<head><title>Assertions Test Page</title></head>
<body>
  <h1>Welcome Page</h1>
  <button id="btn-main" data-testid="btn-main">Click</button>
  <div id="hidden-box" style="display:none;">I am hidden</div>
  <input type="text" id="sample-input" data-testid="sample-input" value="hello">
</body>
</html>
"""


class AssertionHttpHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            content = HTML_ASSERTIONS.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/redirect-to-index":
            self.send_response(302)
            self.send_header("Location", "/index.html")
            self.end_headers()
        elif self.path == "/server-error-500":
            content = b"Internal Server Error"
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def assertion_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), AssertionHttpHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# 1. page_loaded (CASE A, CASE B, CASE C, CASE D)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_page_loaded_pass(assertion_server: str, tmp_path: Path):
    """CASE A: valid route -> PASS"""
    test_def = UITestDefinition(
        id="AST-LOAD-PASS",
        title="Page loaded pass",
        steps=[UITestStep(action="goto", target="/")],
        expected=[UIAssertion(assertion="page_loaded")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True
    assert res.http_status == 200


@pytest.mark.asyncio
async def test_assertion_page_loaded_404_fail(assertion_server: str, tmp_path: Path):
    """CASE B: 404 navigation -> FAIL"""
    test_def = UITestDefinition(
        id="AST-LOAD-404-FAIL",
        title="Page loaded on 404 route must fail",
        steps=[UITestStep(action="goto", target="/checkout-broken")],
        expected=[UIAssertion(assertion="page_loaded")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False
    assert res.http_status == 404
    assert "HTTP 404" in (res.assertions[0].error or res.error or "")


@pytest.mark.asyncio
async def test_assertion_page_loaded_500_fail(assertion_server: str, tmp_path: Path):
    """CASE C: 500 navigation -> FAIL"""
    test_def = UITestDefinition(
        id="AST-LOAD-500-FAIL",
        title="Page loaded on 500 route must fail",
        steps=[UITestStep(action="goto", target="/server-error-500")],
        expected=[UIAssertion(assertion="page_loaded")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False
    assert res.http_status == 500
    assert "HTTP 500" in (res.assertions[0].error or res.error or "")


@pytest.mark.asyncio
async def test_assertion_page_loaded_valid_redirect(assertion_server: str, tmp_path: Path):
    """CASE D: valid redirect -> behaves correctly (follows redirect and passes)"""
    test_def = UITestDefinition(
        id="AST-LOAD-REDIRECT-PASS",
        title="Page loaded on valid redirect must pass",
        steps=[UITestStep(action="goto", target="/redirect-to-index")],
        expected=[
            UIAssertion(assertion="page_loaded"),
            UIAssertion(assertion="http_status", expected="200"),
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True
    assert res.assertions[1].passed is True
    assert res.http_status == 200


# ---------------------------------------------------------------------------
# 2. url_matches (PASS & FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_url_matches_pass(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-URL-PASS",
        title="URL matches pass",
        steps=[UITestStep(action="goto", target="/index.html")],
        expected=[UIAssertion(assertion="url_matches", expected=r"/index\.html$")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True


@pytest.mark.asyncio
async def test_assertion_url_matches_fail(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-URL-FAIL",
        title="URL matches fail",
        steps=[UITestStep(action="goto", target="/")],
        expected=[UIAssertion(assertion="url_matches", expected=r"/wrong-url$")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False
    assert "Assertion failed" in (res.error or "")


# ---------------------------------------------------------------------------
# 3. text_visible (PASS & FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_text_visible_pass(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-TXT-PASS",
        title="Text visible pass",
        steps=[UITestStep(action="goto", target="/")],
        expected=[UIAssertion(assertion="text_visible", expected="Welcome Page")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True


@pytest.mark.asyncio
async def test_assertion_text_visible_fail(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-TXT-FAIL",
        title="Text visible fail",
        steps=[UITestStep(action="goto", target="/")],
        expected=[UIAssertion(assertion="text_visible", expected="Nonexistent Text Impossible")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False


# ---------------------------------------------------------------------------
# 4. element_visible (PASS & FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_element_visible_pass(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-EVIS-PASS",
        title="Element visible pass",
        steps=[UITestStep(action="goto", target="/")],
        expected=[
            UIAssertion(
                assertion="element_visible",
                selector=SelectorSpec(strategy="id", value="btn-main"),
            )
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True


@pytest.mark.asyncio
async def test_assertion_element_visible_fail(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-EVIS-FAIL",
        title="Element visible fail on display:none",
        steps=[UITestStep(action="goto", target="/")],
        expected=[
            UIAssertion(
                assertion="element_visible",
                selector=SelectorSpec(strategy="id", value="hidden-box"),
            )
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False


# ---------------------------------------------------------------------------
# 5. element_hidden (PASS & FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_element_hidden_pass(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-EHID-PASS",
        title="Element hidden pass",
        steps=[UITestStep(action="goto", target="/")],
        expected=[
            UIAssertion(
                assertion="element_hidden",
                selector=SelectorSpec(strategy="id", value="hidden-box"),
            )
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True


@pytest.mark.asyncio
async def test_assertion_element_hidden_fail(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-EHID-FAIL",
        title="Element hidden fail on visible element",
        steps=[UITestStep(action="goto", target="/")],
        expected=[
            UIAssertion(
                assertion="element_hidden",
                selector=SelectorSpec(strategy="id", value="btn-main"),
            )
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False


# ---------------------------------------------------------------------------
# 6. input_value (PASS & FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_input_value_pass(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-INPV-PASS",
        title="Input value pass",
        steps=[UITestStep(action="goto", target="/")],
        expected=[
            UIAssertion(
                assertion="input_value",
                selector=SelectorSpec(strategy="id", value="sample-input"),
                expected="hello",
            )
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True


@pytest.mark.asyncio
async def test_assertion_input_value_fail(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-INPV-FAIL",
        title="Input value fail",
        steps=[UITestStep(action="goto", target="/")],
        expected=[
            UIAssertion(
                assertion="input_value",
                selector=SelectorSpec(strategy="id", value="sample-input"),
                expected="wrong_value",
            )
        ],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False


# ---------------------------------------------------------------------------
# 7. http_status (PASS & FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assertion_http_status_pass(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-HTTP-PASS",
        title="HTTP status pass",
        steps=[UITestStep(action="goto", target="/")],
        expected=[UIAssertion(assertion="http_status", expected="200")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.PASS
    assert res.assertions[0].passed is True


@pytest.mark.asyncio
async def test_assertion_http_status_fail(assertion_server: str, tmp_path: Path):
    test_def = UITestDefinition(
        id="AST-HTTP-FAIL",
        title="HTTP status fail",
        steps=[UITestStep(action="goto", target="/")],
        expected=[UIAssertion(assertion="http_status", expected="404")],
    )
    runner = PlaywrightTestRunner(assertion_server, "run-1", "sess-1", test_def, tmp_path)
    res = await runner.run()
    assert res.status == TestResultStatus.FAIL
    assert res.assertions[0].passed is False
