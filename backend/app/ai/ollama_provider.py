"""
Ollama AI Provider — V1 Default (free, local).

Communicates with a local Ollama instance via its HTTP API.
No API key required. Requires Ollama to be installed and running.

This provider is a stub for Phase 1 — actual AI integration
happens in Phase 4+ (test generation, failure analysis).
"""

import json
import logging

import httpx

from app.ai.base import AIProvider
from app.config import settings

logger = logging.getLogger("testq.ai.ollama")


class OllamaProvider(AIProvider):
    """Ollama local AI provider."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
    ):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ai_model
        self.api_url = f"{self.host}/api"

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        """Generate text using Ollama."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if response_format:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.api_url}/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """Generate structured JSON using Ollama."""
        text = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt + "\nRespond ONLY with valid JSON.",
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json"},
        )

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse AI JSON response: {text[:200]}")
            return {"error": "Failed to parse JSON", "raw": text[:500]}

    async def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_names = [m.get("name", "").split(":")[0] for m in models]
                    if self.model.split(":")[0] in model_names:
                        return True
                    logger.warning(
                        f"Ollama running but model '{self.model}' not found. "
                        f"Available: {model_names}"
                    )
                    return False
                return False
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False
