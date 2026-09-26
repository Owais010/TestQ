"""Phase 3 Deterministic Baseline Test Generator.
Generates structured, executable test definitions directly from the Phase 2 ApplicationMap.
Deterministic: NO AI, NO heuristics, pure reproducible mapping.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Sequence

from app.models.test_case import TestCase
from app.schemas.test_case import (
    UITestDefinition,
    UITestStep,
    UIAssertion,
    APITestDefinition,
    APIRequestSpec,
    APIAssertion,
    SelectorSpec,
    validate_test_definition,
)
from testq_browser.schemas import ApplicationMap


def _relative_path(url: str, base_url: str) -> str:
    """Extract path from URL relative to base_url."""
    try:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path
    except Exception:
        return "/"


class BaselineGenerator:
    """Generates a predictable baseline test suite from an ApplicationMap."""

    @classmethod
    def generate_suite(cls, app_map: ApplicationMap, run_id: str) -> list[TestCase]:
        """Generate a deterministic baseline suite based on discovered application pages and endpoints."""
        cases: list[TestCase] = []
        base_url = app_map.base_url

        # -------------------------------------------------------------------
        # 1. HOME-001: Homepage loads
        # -------------------------------------------------------------------
        home_def = UITestDefinition(
            id="HOME-001",
            type="ui",
            title="Homepage loads successfully",
            priority="critical",
            steps=[
                UITestStep(action="goto", target="/", timeout_ms=5000),
            ],
            expected=[
                UIAssertion(assertion="page_loaded"),
                UIAssertion(assertion="http_status", expected="200"),
            ],
        )
        cases.append(TestCase(
            run_id=run_id,
            type="ui",
            title=home_def.title,
            priority=home_def.priority,
            definition=home_def.model_dump(mode="json"),
        ))

        # -------------------------------------------------------------------
        # 2. NAV-xxx: Discovered internal routes
        # -------------------------------------------------------------------
        seen_paths = {"/"}
        nav_idx = 1
        for page in app_map.pages:
            path = _relative_path(page.url, base_url)
            if path in seen_paths or not path.startswith("/"):
                continue
            seen_paths.add(path)

            test_id = f"NAV-{nav_idx:03d}"
            nav_idx += 1

            nav_def = UITestDefinition(
                id=test_id,
                type="ui",
                title=f"Internal route {path} loads",
                priority="high",
                steps=[
                    UITestStep(action="goto", target=path, timeout_ms=5000),
                ],
                expected=[
                    UIAssertion(assertion="page_loaded"),
                    UIAssertion(assertion="url_matches", expected=re.escape(path)),
                ],
            )
            cases.append(TestCase(
                run_id=run_id,
                type="ui",
                title=nav_def.title,
                priority=nav_def.priority,
                definition=nav_def.model_dump(mode="json"),
            ))
            if nav_idx > 5:
                break

        # -------------------------------------------------------------------
        # 3. UI-xxx: Discovered elements (forms and inputs)
        # -------------------------------------------------------------------
        ui_idx = 1
        for page in app_map.pages:
            path = _relative_path(page.url, base_url)
            # Forms
            for form in page.forms:
                test_id = f"UI-FORM-{ui_idx:03d}"
                ui_idx += 1
                selector_cand = None
                if form.identifier:
                    selector_cand = SelectorSpec(strategy="id", value=form.identifier)
                elif form.action:
                    selector_cand = SelectorSpec(strategy="css", value=f'form[action="{form.action}"]')
                else:
                    selector_cand = SelectorSpec(strategy="css", value="form")

                form_def = UITestDefinition(
                    id=test_id,
                    type="ui",
                    title=f"Form on {path} is visible",
                    priority="medium",
                    steps=[
                        UITestStep(action="goto", target=path, timeout_ms=5000),
                    ],
                    expected=[
                        UIAssertion(assertion="element_visible", selector=selector_cand),
                    ],
                )
                cases.append(TestCase(
                    run_id=run_id,
                    type="ui",
                    title=form_def.title,
                    priority=form_def.priority,
                    definition=form_def.model_dump(mode="json"),
                ))
                if ui_idx > 3:
                    break

            # Inputs
            for inp in page.inputs:
                if not inp.selectors:
                    continue
                test_id = f"UI-INP-{ui_idx:03d}"
                ui_idx += 1

                first_sel = inp.selectors[0]
                sel_spec = SelectorSpec(
                    strategy=first_sel.strategy,
                    value=first_sel.value,
                    role=first_sel.role,
                    exact=first_sel.exact,
                )

                inp_def = UITestDefinition(
                    id=test_id,
                    type="ui",
                    title=f"Input on {path} is visible",
                    priority="medium",
                    steps=[
                        UITestStep(action="goto", target=path, timeout_ms=5000),
                    ],
                    expected=[
                        UIAssertion(assertion="element_visible", selector=sel_spec),
                    ],
                )
                cases.append(TestCase(
                    run_id=run_id,
                    type="ui",
                    title=inp_def.title,
                    priority=inp_def.priority,
                    definition=inp_def.model_dump(mode="json"),
                ))
                if ui_idx > 6:
                    break
            if ui_idx > 6:
                break

        # 3b. UI-ACT-001: Interactive controls test if controls exist
        for page in app_map.pages:
            path = _relative_path(page.url, base_url)
            interactive_steps: list[UITestStep] = [UITestStep(action="goto", target=path, timeout_ms=5000)]
            interactive_expected: list[UIAssertion] = [UIAssertion(assertion="page_loaded")]

            all_inputs = list(page.inputs)
            all_buttons = list(page.buttons)
            for form in page.forms:
                all_inputs.extend(form.controls)
                all_buttons.extend(form.buttons)

            seen_values = set()
            for inp in all_inputs:
                if not inp.selectors:
                    continue
                first_sel = inp.selectors[0]
                sel_spec = SelectorSpec(
                    strategy=first_sel.strategy,
                    value=first_sel.value,
                    role=first_sel.role,
                    exact=first_sel.exact,
                )
                if first_sel.value in seen_values:
                    continue
                seen_values.add(first_sel.value)

                inp_type = (inp.input_type or "").lower()
                tag = (inp.tag or "").lower()

                if tag == "select" or inp.options:
                    opt_val = inp.options[0] if inp.options else "user"
                    interactive_steps.append(UITestStep(action="select", selector=sel_spec, value=opt_val, timeout_ms=3000))
                elif inp_type == "checkbox":
                    interactive_steps.append(UITestStep(action="check", selector=sel_spec, timeout_ms=3000))
                    interactive_steps.append(UITestStep(action="uncheck", selector=sel_spec, timeout_ms=3000))
                elif inp_type in ("text", "email", "search", "") and tag == "input":
                    interactive_steps.append(UITestStep(action="fill", selector=sel_spec, value="tester", timeout_ms=3000))
                    interactive_expected.append(UIAssertion(assertion="input_value", selector=sel_spec, expected="tester"))

            for btn in all_buttons:
                if not btn.selectors:
                    continue
                first_sel = btn.selectors[0]
                if first_sel.value in seen_values:
                    continue
                seen_values.add(first_sel.value)
                btn_spec = SelectorSpec(
                    strategy=first_sel.strategy,
                    value=first_sel.value,
                    role=first_sel.role,
                    exact=first_sel.exact,
                )
                interactive_steps.append(UITestStep(action="click", selector=btn_spec, timeout_ms=3000))
                break

            if len(interactive_steps) > 1:
                act_def = UITestDefinition(
                    id="UI-ACT-001",
                    type="ui",
                    title=f"Interact with controls on {path}",
                    priority="high",
                    steps=interactive_steps,
                    expected=interactive_expected,
                )
                cases.append(TestCase(
                    run_id=run_id,
                    type="ui",
                    title=act_def.title,
                    priority=act_def.priority,
                    definition=act_def.model_dump(mode="json"),
                ))
                break

        # -------------------------------------------------------------------
        # 4. API-xxx: Discovered API endpoints
        # -------------------------------------------------------------------
        api_idx = 1
        seen_api_paths = set()
        for ep in app_map.api_endpoints:
            path = ep.path if ep.path.startswith("/") else f"/{ep.path}"
            method = ep.method.upper()
            if (method, path) in seen_api_paths or method not in ("GET", "HEAD", "OPTIONS"):
                continue
            seen_api_paths.add((method, path))

            test_id = f"API-{api_idx:03d}"
            api_idx += 1

            expected_assertions = [
                APIAssertion(assertion="status_code", expected=200),
                APIAssertion(assertion="response_time", expected=5000),
            ]
            if path.startswith("/api/"):
                expected_assertions.append(APIAssertion(assertion="content_type", expected="application/json"))
            if path in ("/api/health", "/health"):
                expected_assertions.append(APIAssertion(assertion="json_field_present", field="status"))
                expected_assertions.append(APIAssertion(assertion="json_value", field="status", expected="ok"))

            api_def = APITestDefinition(
                id=test_id,
                type="api",
                title=f"API {method} {path} responds",
                priority="high",
                request=APIRequestSpec(
                    method=method,
                    path=path,
                    timeout_ms=5000,
                ),
                expected=expected_assertions,
            )
            cases.append(TestCase(
                run_id=run_id,
                type="api",
                title=api_def.title,
                priority=api_def.priority,
                definition=api_def.model_dump(mode="json"),
            ))
            if api_idx > 5:
                break

        # Strictly validate every generated definition before returning
        for tc in cases:
            validate_test_definition(tc.definition)

        return cases
