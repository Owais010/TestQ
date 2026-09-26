"""Phase 4 AI Test Generator.
Generates structured, executable UI and API test cases based on the QA TestStrategy and ApplicationMap.
Validates through strict Pydantic schemas, enforces security boundaries, and deterministically deduplicates.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from app.ai.base import (
    AIProvider,
    AIError,
    AIUnavailableError,
    AITimeoutError,
    AISchemaValidationError,
    AIInvalidOutputError,
)
from app.config import settings
from app.models.test_case import TestCase
from app.schemas.ai_test import TestStrategy, AITestGenerationOutput
from app.schemas.test_case import (
    UITestDefinition,
    APITestDefinition,
    validate_test_definition,
    SelectorSpec,
)
from testq_browser.schemas import ApplicationMap

logger = logging.getLogger("testq.ai.generator")

GENERATOR_SYSTEM_PROMPT = "You are the TestQ AI Test Generator. You output valid JSON test suites only."


class TestGenerator:
    """Generates and validates executable tests from strategy items."""
    __test__ = False

    def __init__(
        self,
        ai_provider: AIProvider,
        max_tests: int | None = None,
        max_retries: int | None = None,
    ):
        self.ai = ai_provider
        self.max_tests = max_tests or settings.ai_max_generated_tests
        self.max_retries = max_retries if max_retries is not None else settings.ai_max_retries

    async def generate(
        self,
        strategy: TestStrategy,
        app_map: ApplicationMap,
        run_id: str,
        baseline_cases: Sequence[TestCase] | None = None,
    ) -> list[TestCase]:
        """Generate structured test definitions from strategy, validate, deduplicate and return TestCase models."""
        if not strategy.items:
            logger.info("No strategy items provided; skipping AI test generation")
            return []

        context = self._build_generation_context(strategy, app_map)

        strategy_lines = [
            f"- Category: {item.category}, Target: {item.target}, Description: {item.description}"
            for item in strategy.items
        ]
        strategy_text = "\n".join(strategy_lines)

        schema_example = (
            "{\n"
            '  "ui_tests": [\n'
            "    {\n"
            '      "id": "AI-UI-001",\n'
            '      "type": "ui",\n'
            '      "title": "Verify homepage loads",\n'
            '      "priority": "high",\n'
            '      "steps": [\n'
            '        {"action": "goto", "target": "/"}\n'
            "      ],\n"
            '      "expected": [\n'
            '        {"assertion": "page_loaded"}\n'
            "      ]\n"
            "    }\n"
            "  ],\n"
            '  "api_tests": []\n'
            "}"
        )

        base_prompt = (
            "APPLICATION MAP:\n"
            f"{context}\n\n"
            "STRATEGY ITEMS:\n"
            f"{strategy_text}\n\n"
            "RULES FOR HIGH QUALITY TESTS:\n"
            "- Targets in steps must be relative paths (e.g. '/', '/checkout') or element text from the APPLICATION MAP.\n"
            "- Never assert hardcoded external domain names; use page_loaded, text_visible, or relative url regex (e.g. '/$') for url_matches.\n"
            "- Do not invent non-existent buttons or fields; test real interactive elements listed in the APPLICATION MAP.\n\n"
            "STRICT OUTPUT SCHEMA:\n"
            f"{schema_example}\n\n"
            f"Generate 2 to {self.max_tests} concrete executable tests.\n"
            "OUTPUT JSON ONLY.\n"
            "No markdown. No code fences. No prose. No comments. No additional keys."
        )

        last_error: Exception | None = None
        current_prompt = base_prompt

        for attempt in range(self.max_retries + 1):
            try:
                result = await self.ai.generate(
                    prompt=current_prompt,
                    system_prompt=GENERATOR_SYSTEM_PROMPT,
                    response_schema=AITestGenerationOutput,
                    timeout=settings.ai_generator_timeout,
                )
                generated_output = AITestGenerationOutput.model_validate(result)
                logger.info(
                    "Raw generated output (attempt %d): %d UI tests, %d API tests",
                    attempt + 1,
                    len(generated_output.ui_tests),
                    len(generated_output.api_tests),
                )

                valid_cases, validation_errors = self._process_generated_tests(
                    generated_output=generated_output,
                    run_id=run_id,
                    baseline_cases=baseline_cases or [],
                )

                if valid_cases:
                    logger.info(
                        "AI Test Generator produced %d validated test cases (attempt %d)",
                        len(valid_cases), attempt + 1
                    )
                    return valid_cases

                # 0 valid cases produced
                if validation_errors:
                    err_msg = "\n".join(validation_errors[:3])
                    logger.warning(
                        "AI GENERATOR VALIDATION FAILURE (Attempt %d/%d)\nReason:\n%s",
                        attempt + 1, self.max_retries + 1, err_msg
                    )
                    last_error = AISchemaValidationError(err_msg)
                    if attempt < self.max_retries:
                        current_prompt = (
                            f"AI GENERATOR SCHEMA CORRECTION:\n"
                            f"Your previous output was invalid because:\n{err_msg}\n\n"
                            f"REQUIRED SCHEMA:\n{schema_example}\n\n"
                            f"Rules:\n"
                            f"- UI steps: action must be one of: goto, click, fill, select, check, uncheck, wait. Target must be a path like '/' or element name.\n"
                            f"- UI expected: assertion must be one of: page_loaded, text_visible, url_matches, element_visible, http_status.\n"
                            f"Return corrected JSON ONLY. No markdown, no prose."
                        )
                else:
                    logger.warning("AI generator returned 0 test items on attempt %d", attempt + 1)
                    last_error = AIInvalidOutputError("Model returned empty test suite")
                    if attempt < self.max_retries:
                        current_prompt = (
                            f"Your previous output was empty. Please generate 2 to {self.max_tests} concrete tests matching:\n"
                            f"{schema_example}\n\n"
                            "Return JSON ONLY."
                        )

            except (AIUnavailableError, AITimeoutError):
                raise
            except (AISchemaValidationError, AIInvalidOutputError) as e:
                last_error = e
                logger.warning("Generator output validation failed on attempt %d: %s", attempt + 1, e)
                if attempt < self.max_retries:
                    current_prompt = (
                        f"Previous output failed validation: {e}\n\n"
                        f"REQUIRED SCHEMA:\n{schema_example}\n\n"
                        "Return corrected JSON ONLY."
                    )
            except Exception as e:
                last_error = e
                logger.warning("Unexpected error during test generation attempt %d: %s", attempt + 1, e)

        raise AISchemaValidationError(
            f"Generated output did not satisfy TestQ's executable test schema: {last_error}"
        )

    def _process_generated_tests(
        self,
        generated_output: AITestGenerationOutput,
        run_id: str,
        baseline_cases: Sequence[TestCase],
    ) -> tuple[list[TestCase], list[str]]:
        """Validate against Phase 3 schema, enforce security rules, and deduplicate."""
        all_raw_tests: list[UITestDefinition | APITestDefinition] = []
        all_raw_tests.extend(generated_output.ui_tests)
        all_raw_tests.extend(generated_output.api_tests)

        # Build signatures of existing baseline cases for deduplication
        existing_signatures = {self._test_signature(tc.definition) for tc in baseline_cases}

        validated_cases: list[TestCase] = []
        validation_errors: list[str] = []
        seen_generated_signatures = set()

        ui_counter = 1
        api_counter = 1

        for raw_test in all_raw_tests:
            # 1. Enforce max tests limit
            if len(validated_cases) >= self.max_tests:
                break

            # 2. Strict Phase 3 Schema Validation
            try:
                test_dict = raw_test if isinstance(raw_test, dict) else raw_test.model_dump(mode="json")
                validated_def = validate_test_definition(test_dict)
            except Exception as ve:
                err_desc = f"{test_dict.get('id', '?') if isinstance(raw_test, dict) else getattr(raw_test, 'id', '?')}: {ve}"
                logger.warning("Discarding invalid generated test %s", err_desc)
                validation_errors.append(err_desc)
                continue

            # 3. Security Boundary Checks: no external URLs, only relative paths
            if isinstance(validated_def, UITestDefinition):
                if any(
                    (step.target and step.target.startswith(("http://", "https://", "//")))
                    for step in validated_def.steps
                ):
                    logger.warning("Discarding test with external URL: %s", validated_def.id)
                    continue
            elif isinstance(validated_def, APITestDefinition):
                if validated_def.request.path.startswith(("http://", "https://", "//")):
                    logger.warning("Discarding API test with external URL: %s", validated_def.id)
                    continue

            # 4. Deterministic Deduplication
            sig = self._test_signature(test_dict)
            if sig in existing_signatures or sig in seen_generated_signatures:
                logger.debug("Deduplicated equivalent test: %s (signature: %s)", validated_def.id, sig[:60])
                continue

            seen_generated_signatures.add(sig)

            # 5. Namespace ID correctly
            if isinstance(validated_def, UITestDefinition):
                test_id = f"AI-UI-{ui_counter:03d}"
                ui_counter += 1
            else:
                test_id = f"AI-API-{api_counter:03d}"
                api_counter += 1

            test_dict["id"] = test_id

            validated_cases.append(
                TestCase(
                    run_id=run_id,
                    type=validated_def.type,
                    title=validated_def.title,
                    priority=validated_def.priority,
                    source="ai",
                    definition=test_dict,
                )
            )

        return validated_cases, validation_errors

    @staticmethod
    def _test_signature(definition: dict[str, Any]) -> str:
        """Compute a deterministic signature for deduplication."""
        test_type = definition.get("type", "ui")
        if test_type == "ui":
            steps = definition.get("steps", [])
            steps_sig = []
            for s in steps:
                act = s.get("action")
                tgt = s.get("target") or ""
                sel = s.get("selector", {}) or {}
                sel_val = f"{sel.get('strategy')}:{sel.get('value')}" if sel else ""
                val = s.get("value") or ""
                t_ms = s.get("timeout_ms") or ""
                steps_sig.append(f"{act}|{tgt}|{sel_val}|{val}|{t_ms}")
            expected = definition.get("expected", [])
            exp_sig = [f"{e.get('assertion')}|{e.get('expected')}" for e in expected]
            return f"ui:steps={'#'.join(steps_sig)}:exp={'#'.join(exp_sig)}"
        else:
            req = definition.get("request", {})
            method = req.get("method", "GET").upper()
            path = req.get("path", "/")
            expected = definition.get("expected", [])
            exp_sig = [f"{e.get('assertion')}|{e.get('field')}|{e.get('expected')}" for e in expected]
            return f"api:{method}:{path}:exp={'#'.join(exp_sig)}"

    def _build_generation_context(
        self, strategy: TestStrategy, app_map: ApplicationMap
    ) -> str:
        """Build safe context pairing strategy items with concrete element targets."""
        data: dict[str, Any] = {
            "strategy_items": [item.model_dump(mode="json") for item in strategy.items],
            "available_page_elements": {},
            "available_api_endpoints": [],
        }

        base_url = app_map.base_url.rstrip("/")

        for p in app_map.pages:
            rel_url = p.url[len(base_url):] if p.url.startswith(base_url) else p.url
            if not rel_url.startswith("/"):
                rel_url = f"/{rel_url}"

            elements = []
            for btn in p.buttons[:6]:
                name = btn.accessible_name or btn.text or "button"
                elements.append({"target": name, "role": "button"})

            for inp in p.inputs[:6]:
                name = inp.name or inp.element_id or "input"
                elements.append({"target": name, "type": inp.input_type or inp.tag})

            data["available_page_elements"][rel_url] = elements

        for ep in app_map.api_endpoints[:6]:
            data["available_api_endpoints"].append({
                "method": ep.method,
                "path": ep.path,
            })

        return json.dumps(data, indent=2)
