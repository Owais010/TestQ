"""Local Ollama provider implementation.
TestQ MVP remains 100% free by running local open-weights models through Ollama.
No cloud dependencies, no paid APIs, and no execution privileges.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.base import (
    AIError,
    AIProvider,
    AIUnavailableError,
    AITimeoutError,
    AIInvalidOutputError,
    AISchemaValidationError,
    AIGenerationLimitError,
)
from app.config import settings

logger = logging.getLogger("testq.ai.ollama")


class OllamaProvider(AIProvider):
    """Local Ollama client communicating over HTTP loopback."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_output_bytes: int | None = None,
    ):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ai_model
        self.timeout = timeout or settings.ai_request_timeout
        self.max_output_bytes = max_output_bytes or settings.ai_max_output_bytes

    async def is_available(self) -> bool:
        """Check if local Ollama daemon is active and configured model exists."""
        try:
            timeout_sec = getattr(settings, "ai_preflight_timeout", 15.0)
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                res = await client.get(f"{self.host}/api/tags")
                if res.status_code != 200:
                    return False
                models = res.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                target_base = self.model.split(":")[0]
                installed_bases = [m.split(":")[0] for m in model_names]
                return self.model in model_names or target_base in installed_bases
        except Exception:
            return False

    async def preflight(self) -> dict[str, Any]:
        """Perform preflight checks:
        1. Check Ollama availability.
        2. Check /api/tags.
        3. Verify configured model exists.
        4. Perform lightweight warm-up request.
        Returns:
            Dict with status ("READY" | "WARMING" | "UNAVAILABLE" | "ERROR"),
            ready boolean, model name, and diagnostic message.
        """
        timeout_sec = getattr(settings, "ai_preflight_timeout", 15.0)

        # 1 & 2. Check availability and list installed models
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                res = await client.get(f"{self.host}/api/tags")
                if res.status_code != 200:
                    return {
                        "status": "ERROR",
                        "ready": False,
                        "model": self.model,
                        "host": self.host,
                        "installed_models": [],
                        "message": f"Ollama returned HTTP error {res.status_code}",
                    }
                models = res.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            return {
                "status": "UNAVAILABLE",
                "ready": False,
                "model": self.model,
                "host": self.host,
                "installed_models": [],
                "message": f"Ollama daemon unreachable at {self.host}: {e}",
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "ready": False,
                "model": self.model,
                "host": self.host,
                "installed_models": [],
                "message": f"Ollama preflight request failed: {e}",
            }

        # 3. Verify configured model exists
        target_base = self.model.split(":")[0]
        installed_bases = [m.split(":")[0] for m in model_names]
        model_found = self.model in model_names or target_base in installed_bases
        if not model_found:
            return {
                "status": "UNAVAILABLE",
                "ready": False,
                "model": self.model,
                "host": self.host,
                "installed_models": model_names,
                "message": f"Configured model '{self.model}' is not installed in Ollama. Available: {model_names or ['none']}",
            }

        # 4. Lightweight warm-up ping
        try:
            warmup_timeout = min(25.0, timeout_sec + 10)
            async with httpx.AsyncClient(timeout=warmup_timeout) as client:
                ping_res = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": "ping",
                        "stream": False,
                        "options": {"num_predict": 1},
                    },
                )
                if ping_res.status_code == 200:
                    return {
                        "status": "READY",
                        "ready": True,
                        "model": self.model,
                        "host": self.host,
                        "installed_models": model_names,
                        "message": f"Model '{self.model}' is ready and responsive",
                    }
                else:
                    return {
                        "status": "WARMING",
                        "ready": True,
                        "model": self.model,
                        "host": self.host,
                        "installed_models": model_names,
                        "message": f"Model '{self.model}' installed (warm-up returned HTTP {ping_res.status_code})",
                    }
        except (httpx.ReadTimeout, httpx.WriteTimeout, asyncio.TimeoutError):
            return {
                "status": "WARMING",
                "ready": True,
                "model": self.model,
                "host": self.host,
                "installed_models": model_names,
                "message": f"Model '{self.model}' is installed and warming into memory",
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "ready": False,
                "model": self.model,
                "host": self.host,
                "installed_models": model_names,
                "message": f"Model warm-up ping failed: {e}",
            }

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_schema: type[BaseModel] | None = None,
        timeout: float | None = None,
    ) -> str | dict[str, Any]:
        """Send a generation request to the local Ollama instance."""
        req_timeout = timeout or self.timeout
        endpoint = f"{self.host}/api/generate"

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        if "qwen" in self.model.lower() and "<think>" not in full_prompt:
            full_prompt = f"{full_prompt}\n<think>\n</think>"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            },
        }
        if response_schema is not None:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=req_timeout) as client:
                response = await client.post(endpoint, json=payload)
                if response.status_code >= 400:
                    raise AIError(f"Ollama returned HTTP error {response.status_code}: {response.text[:200]}")
                data = response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.warning("Local Ollama service unreachable at %s: %s", self.host, e)
            raise AIUnavailableError(f"Ollama service unavailable at {self.host}: {e}") from e
        except (httpx.ReadTimeout, httpx.WriteTimeout, asyncio.TimeoutError) as e:
            logger.warning("Ollama request timed out after %.1fs", req_timeout)
            raise AITimeoutError(f"Ollama request timed out after {req_timeout:.1f}s") from e
        except AIError:
            raise
        except Exception as e:
            logger.error("Unexpected Ollama error: %s", e)
            raise AIError(f"Ollama request failed: {e}") from e

        raw_text = data.get("response", "")
        done_reason = data.get("done_reason", "unknown")
        prompt_eval_count = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)
        logger.info(
            "Ollama response: %d bytes, done_reason=%s, prompt_tokens=%d, output_tokens=%d",
            len(raw_text), done_reason, prompt_eval_count, eval_count,
        )
        if not raw_text and not data.get("done", False):
            raise AIInvalidOutputError("Empty or incomplete response from Ollama")

        # Check output size boundary
        if len(raw_text.encode("utf-8")) > self.max_output_bytes:
            raise AIGenerationLimitError(
                f"Model output size ({len(raw_text)} bytes) exceeded limit of {self.max_output_bytes} bytes"
            )

        if response_schema is None:
            return raw_text

        # Strip optional markdown code fences ```json ... ```
        cleaned_text = self._strip_code_fences(raw_text.strip())

        try:
            parsed_json = json.loads(cleaned_text)
            logger.info("Ollama raw text (%d bytes): %s", len(raw_text), raw_text[:300])
            logger.info("Ollama parsed JSON: %s", json.dumps(parsed_json)[:300])
        except json.JSONDecodeError as e:
            recovered = self._recover_partial_json(cleaned_text)
            if recovered and (recovered.get("ui_tests") or recovered.get("api_tests")):
                parsed_json = recovered
                logger.info("Recovered %d UI tests, %d API tests from partial JSON response",
                            len(recovered.get("ui_tests", [])), len(recovered.get("api_tests", [])))
            else:
                logger.warning("Failed to parse JSON from Ollama response: %s", raw_text[:300])
                raise AIInvalidOutputError(f"Model output is not valid JSON: {e}") from e

        try:
            validated = response_schema.model_validate(parsed_json)
            return validated.model_dump(mode="json")
        except ValidationError as ve:
            logger.debug("Schema validation failed for Ollama output: %s", ve)
            raise AISchemaValidationError(f"Model output failed schema validation: {ve}") from ve

    @staticmethod
    def _recover_partial_json(raw_text: str) -> dict[str, Any] | None:
        """Extract completed balanced test objects from truncated JSON."""
        tests = []
        stack = []
        for i, ch in enumerate(raw_text):
            if ch == '{':
                stack.append(i)
            elif ch == '}':
                if stack:
                    s = stack.pop()
                    if len(stack) == 1:
                        candidate = raw_text[s:i+1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict) and ("steps" in obj or "request" in obj or "assertion" in obj):
                                tests.append(obj)
                        except Exception:
                            pass
        if tests:
            ui = [t for t in tests if "steps" in t or t.get("type") == "ui"]
            api = [t for t in tests if "request" in t or t.get("type") == "api"]
            return {"ui_tests": ui, "api_tests": api}
        return None

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Safely remove surrounding markdown code blocks if the model outputs them."""
        fenced_pattern = r"^```(?:json)?\s*([\s\S]*?)\s*```$"
        match = re.match(fenced_pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1).strip()
        return text
