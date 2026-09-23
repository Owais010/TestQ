"""
AI Provider Base — Abstract interface for AI providers.

V1 default: Ollama (local, free).
Architecture supports adding OpenAI, Gemini, etc. later.
"""

from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        """Generate a text response from the AI model."""
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """Generate a structured JSON response from the AI model."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        ...
