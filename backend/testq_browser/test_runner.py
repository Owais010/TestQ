"""In-sandbox Playwright test runner.
Runs inside the TestQ sandbox container, executing deterministic UI tests.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Page, Locator, Error as PlaywrightError, TimeoutError as PlaywrightTimeout

from testq_browser.test_schemas import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    SelectorSpec,
    StepResult,
    AssertionResult,
    TestExecutionResult,
    TestResultStatus,
)
from testq_browser.policies import same_origin, safe_url, redact


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def resolve_unique_locator(page: Page, spec_provider: UITestStep | UIAssertion) -> Locator:
    """Resolve a single unique locator using candidate priority order.
    
    Priority order:
    1. test_id
    2. role / accessible_name
    3. id
    4. name
    5. stable attribute
    6. css
    
    Strict rule: locator.count() must equal 1.
    If none matches uniquely, raises ValueError (with clear error for ambiguous match or not found).
    """
    candidates: list[SelectorSpec] = []
    if getattr(spec_provider, "candidates", None):
        candidates.extend(spec_provider.candidates)
    if getattr(spec_provider, "selector", None) and spec_provider.selector:
        if spec_provider.selector not in candidates:
            candidates.append(spec_provider.selector)
    if getattr(spec_provider, "target", None) and spec_provider.target:
        candidates.append(SelectorSpec(strategy="css", value=spec_provider.target))
    if getattr(spec_provider, "expected", None) and not candidates and getattr(spec_provider, "assertion", None) in ("element_visible", "element_hidden"):
        candidates.append(SelectorSpec(strategy="css", value=spec_provider.expected))

    if not candidates:
        raise ValueError("No selector candidates provided for element resolution")

    # Sort candidates by preferred priority
    strategy_priority = {"test_id": 0, "role": 1, "id": 2, "name": 3, "attribute": 4, "css": 5}
    candidates.sort(key=lambda c: strategy_priority.get(c.strategy, 99))

    ambiguous_count = 0
    last_ambiguous_strategy = None

    for cand in candidates:
        try:
            if cand.strategy == "test_id":
                loc = page.get_by_test_id(cand.value)
            elif cand.strategy == "role":
                loc = page.get_by_role(cand.role or "button", name=cand.value, exact=cand.exact)
            elif cand.strategy == "id":
                loc = page.locator(f"#{cand.value}")
            elif cand.strategy == "name":
                loc = page.locator(f'[name="{cand.value}"]')
            elif cand.strategy == "attribute":
                if "=" in cand.value:
                    attr_name, attr_val = cand.value.split("=", 1)
                    loc = page.locator(f'[{attr_name}="{attr_val}"]')
                else:
                    loc = page.locator(f'[{cand.value}]')
            elif cand.strategy == "css":
                try:
                    loc = page.locator(cand.value)
                    count = await loc.count()
                except Exception:
                    count = 0
                if count != 1:
                    text_loc = page.get_by_text(cand.value, exact=False)
                    try:
                        if await text_loc.count() == 1:
                            loc = text_loc
                        else:
                            btn_loc = page.get_by_role("button", name=cand.value, exact=False)
                            if await btn_loc.count() == 1:
                                loc = btn_loc
                    except Exception:
                        pass
            else:
                continue

            count = await loc.count()
            if count == 1:
                return loc
            elif count > 1:
                ambiguous_count = count
                last_ambiguous_strategy = cand.strategy
        except Exception:
            continue

    if ambiguous_count > 1:
        raise ValueError(
            f"Ambiguous selector match: found {ambiguous_count} matching elements using {last_ambiguous_strategy}"
        )
    raise ValueError(f"Element not found: tried {len(candidates)} selector candidates without a unique match")


class PlaywrightTestRunner:
    """Executes a single UITestDefinition deterministically in Playwright."""

    def __init__(self, base_url: str, run_id: str, session_id: str, test_def: UITestDefinition,
                 output_dir: Path, limits: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.session_id = session_id
        self.test_def = test_def
        self.output_dir = output_dir
        self.limits = limits or {}
        self.action_timeout_ms = int(self.limits.get("action_timeout", 10) * 1000)
        self.nav_timeout_ms = int(self.limits.get("navigation_timeout", 15) * 1000)
        self.test_timeout_ms = int(self.limits.get("test_timeout", 60) * 1000)

        self.console_logs: list[dict] = []
        self.network_events: list[dict] = []
        self.page_errors: list[str] = []
        self.evidence_files: list[str] = []
        self.last_http_status: int | None = None

    async def run(self) -> TestExecutionResult:
        started_at = _utc_now()
        t0 = time.monotonic()
        step_results: list[StepResult] = []
        assertion_results: list[AssertionResult] = []
        status = TestResultStatus.PASS
        error_msg: str | None = None

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                chromium_sandbox=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                locale="en-US",
                timezone_id="UTC",
                reduced_motion="reduce",
                service_workers="block",
                accept_downloads=False,
                permissions=[],
            )
            context.set_default_navigation_timeout(self.nav_timeout_ms)
            context.set_default_timeout(self.action_timeout_ms)

            # Block external navigation
            await context.route("**/*", self._handle_route)
            await context.route_web_socket("**/*", lambda ws: ws.close())

            page = await context.new_page()
            self._attach_page_observers(page)

            try:
                # 1. Execute Steps
                for step in self.test_def.steps:
                    st_time = time.monotonic()
                    step_status = "ok"
                    step_err = None
                    try:
                        await self._execute_step(page, step)
                    except PlaywrightTimeout as te:
                        step_status = "timeout"
                        step_err = f"Step timed out: {te}"
                        status = TestResultStatus.TIMEOUT
                        error_msg = step_err
                        step_results.append(StepResult(
                            action=step.action, target=step.target or (step.selector.value if step.selector else None),
                            status=step_status, duration_ms=(time.monotonic() - st_time) * 1000, error=step_err
                        ))
                        break
                    except Exception as exc:
                        step_status = "error"
                        step_err = redact(str(exc))
                        status = TestResultStatus.ERROR
                        error_msg = step_err
                        step_results.append(StepResult(
                            action=step.action, target=step.target or (step.selector.value if step.selector else None),
                            status=step_status, duration_ms=(time.monotonic() - st_time) * 1000, error=step_err
                        ))
                        break

                    step_results.append(StepResult(
                        action=step.action, target=step.target or (step.selector.value if step.selector else None),
                        status=step_status, duration_ms=(time.monotonic() - st_time) * 1000, error=None
                    ))

                # 2. Evaluate Assertions if steps succeeded
                if status == TestResultStatus.PASS:
                    for assertion in self.test_def.expected:
                        ast_res = await self._evaluate_assertion(page, assertion)
                        assertion_results.append(ast_res)
                        if not ast_res.passed:
                            status = TestResultStatus.FAIL
                            if not error_msg:
                                error_msg = ast_res.error or f"Assertion failed: {ast_res.assertion} (expected {ast_res.expected!r}, got {ast_res.actual!r})"

                # 3. Capture evidence
                # Screenshot
                screenshot_filename = f"screenshot_{self.test_def.id}.png"
                screenshot_path = self.output_dir / screenshot_filename
                try:
                    await page.screenshot(path=str(screenshot_path), full_page=False)
                    self.evidence_files.append(screenshot_filename)
                except Exception:
                    pass

            except asyncio.CancelledError:
                status = TestResultStatus.CANCELLED
                error_msg = "Test execution cancelled"
            except Exception as e:
                status = TestResultStatus.ERROR
                error_msg = redact(str(e))
            finally:
                await context.close()
                await browser.close()

        # Save console logs
        console_filename = f"console_{self.test_def.id}.json"
        try:
            (self.output_dir / console_filename).write_text(
                json.dumps(self.console_logs, indent=2), encoding="utf-8"
            )
            self.evidence_files.append(console_filename)
        except Exception:
            pass

        # Save network events
        network_filename = f"network_{self.test_def.id}.json"
        try:
            (self.output_dir / network_filename).write_text(
                json.dumps(self.network_events, indent=2), encoding="utf-8"
            )
            self.evidence_files.append(network_filename)
        except Exception:
            pass

        duration_ms = (time.monotonic() - t0) * 1000
        finished_at = _utc_now()

        result = TestExecutionResult(
            test_id=self.test_def.id,
            run_id=self.run_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round(duration_ms, 2),
            steps=step_results,
            assertions=assertion_results,
            error=error_msg,
            evidence_files=self.evidence_files,
            http_status=self.last_http_status,
        )

        # Write result json
        result_filename = f"result_{self.test_def.id}.json"
        try:
            (self.output_dir / result_filename).write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            self.evidence_files.append(result_filename)
        except Exception:
            pass

        return result

    async def _handle_route(self, route):
        url = route.request.url
        if same_origin(url, self.base_url):
            await route.continue_()
        else:
            self.network_events.append({
                "url": safe_url(url), "method": route.request.method, "blocked": True
            })
            await route.abort("blockedbyclient")

    def _attach_page_observers(self, page: Page):
        page.on("console", lambda msg: self.console_logs.append({
            "type": msg.type, "text": redact(msg.text, 2000), "timestamp": time.time()
        }))
        page.on("pageerror", lambda err: self.page_errors.append(redact(str(err), 2000)))
        page.on("requestfailed", lambda req: self.network_events.append({
            "url": safe_url(req.url), "method": req.method, "failure": str(req.failure),
        }))
        def _handle_response(resp):
            try:
                if resp.request.is_navigation_request() or resp.url == page.url:
                    self.last_http_status = resp.status
            except Exception:
                pass
        page.on("response", _handle_response)
        page.on("dialog", lambda dialog: dialog.dismiss())
        page.on("popup", lambda popup: popup.close())

    async def _execute_step(self, page: Page, step: UITestStep):
        timeout = step.timeout_ms or self.action_timeout_ms
        if step.action == "goto":
            target_path = step.target if step.target.startswith("/") else f"/{step.target}"
            full_url = f"{self.base_url}{target_path}"
            response = await page.goto(full_url, wait_until="domcontentloaded", timeout=timeout)
            if response:
                self.last_http_status = response.status
            if not same_origin(page.url, self.base_url):
                raise ValueError("Navigation left target application origin")
            await page.wait_for_timeout(min(200, self.action_timeout_ms))

        elif step.action == "click":
            loc = await resolve_unique_locator(page, step)
            await loc.click(timeout=timeout)

        elif step.action == "fill":
            loc = await resolve_unique_locator(page, step)
            await loc.fill(step.value or "", timeout=timeout)

        elif step.action == "select":
            loc = await resolve_unique_locator(page, step)
            await loc.select_option(step.value or "", timeout=timeout)

        elif step.action == "check":
            loc = await resolve_unique_locator(page, step)
            await loc.check(timeout=timeout)

        elif step.action == "uncheck":
            loc = await resolve_unique_locator(page, step)
            await loc.uncheck(timeout=timeout)

        elif step.action == "wait":
            await page.wait_for_timeout(step.timeout_ms or 1000)

    async def _evaluate_assertion(self, page: Page, assertion: UIAssertion) -> AssertionResult:
        ast_name = assertion.assertion
        expected = assertion.expected

        try:
            if ast_name == "page_loaded":
                ready_state = await page.evaluate("document.readyState")
                dom_ready = ready_state in ("interactive", "complete")
                http_ok = True
                if self.last_http_status is not None and self.last_http_status >= 400:
                    http_ok = False
                passed = dom_ready and http_ok
                actual = f"{ready_state} (HTTP {self.last_http_status})" if self.last_http_status is not None else ready_state
                err = None
                if not dom_ready:
                    err = f"DOM ready state was '{ready_state}', expected 'interactive' or 'complete'"
                elif not http_ok:
                    err = f"Navigation returned HTTP {self.last_http_status} (application route failed to serve)"
                return AssertionResult(assertion=ast_name, passed=passed, expected="complete", actual=actual, error=err)

            elif ast_name == "url_matches":
                current_url = page.url
                passed = bool(re.search(expected, current_url)) if expected else False
                return AssertionResult(assertion=ast_name, passed=passed, expected=expected, actual=current_url)

            elif ast_name == "text_visible":
                loc = page.get_by_text(expected)
                count = await loc.count()
                visible = False
                if count > 0:
                    visible = await loc.first.is_visible()
                return AssertionResult(assertion=ast_name, passed=visible, expected=expected, actual=f"visible={visible}")

            elif ast_name == "element_visible":
                loc = await resolve_unique_locator(page, assertion)
                visible = await loc.is_visible()
                return AssertionResult(assertion=ast_name, passed=visible, expected="visible", actual=f"visible={visible}")

            elif ast_name == "element_hidden":
                try:
                    loc = await resolve_unique_locator(page, assertion)
                    hidden = await loc.is_hidden()
                except ValueError as ve:
                    # If element was not found, it is hidden/absent
                    hidden = "not found" in str(ve).lower()
                return AssertionResult(assertion=ast_name, passed=hidden, expected="hidden", actual=f"hidden={hidden}")

            elif ast_name == "input_value":
                loc = await resolve_unique_locator(page, assertion)
                val = await loc.input_value()
                passed = (val == expected)
                return AssertionResult(assertion=ast_name, passed=passed, expected=expected, actual=val)

            elif ast_name == "http_status":
                passed = (self.last_http_status == int(expected)) if self.last_http_status is not None else False
                return AssertionResult(assertion=ast_name, passed=passed, expected=str(expected), actual=str(self.last_http_status))

            else:
                return AssertionResult(assertion=ast_name, passed=False, error=f"Unknown assertion: {ast_name}")

        except Exception as e:
            return AssertionResult(assertion=ast_name, passed=False, error=redact(str(e)))


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python -m testq_browser.test_runner <base64_payload>\n")
        return 1

    payload_json = base64.b64decode(sys.argv[1]).decode("utf-8")
    data = json.loads(payload_json)

    base_url = data["base_url"]
    run_id = data["run_id"]
    session_id = data["session_id"]
    test_def = UITestDefinition.model_validate(data["test_definition"])
    output_dir = Path(data.get("output_dir", f"/discovery/{session_id}"))
    limits = data.get("limits", {})

    runner = PlaywrightTestRunner(base_url, run_id, session_id, test_def, output_dir, limits)
    result = asyncio.run(runner.run())
    sys.stdout.write(result.model_dump_json() + "\n")
    return 0 if result.status == TestResultStatus.PASS else (2 if result.status == TestResultStatus.FAIL else 1)


if __name__ == "__main__":
    raise SystemExit(main())
