"""Factory for retrieving configured AI providers."""
from __future__ import annotations

from app.ai.base import AIProvider
from app.ai.ollama import OllamaProvider
from app.config import settings


def get_ai_provider() -> AIProvider:
    """Return the configured AIProvider instance. Default is local Ollama."""
    provider_name = (settings.ai_provider or "ollama").lower()
    if provider_name == "ollama":
        return OllamaProvider(
            host=settings.ollama_host,
            model=settings.ai_model,
            timeout=settings.ai_request_timeout,
            max_output_bytes=settings.ai_max_output_bytes,
        )
    raise ValueError(f"Unsupported AI provider: {provider_name}. TestQ MVP supports local 'ollama'.")
