"""Phase 4 AI provider abstraction and exception hierarchy.
AI reasons; deterministic code executes.
The AI layer outputs structured data only and has NO execution privileges.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel


class AIError(Exception):
    """Base exception for all AI generation errors."""
    pass


class AIUnavailableError(AIError):
    """Raised when the local AI service (e.g. Ollama) is not running or unreachable."""
    pass


class AITimeoutError(AIError):
    """Raised when the AI model generation times out."""
    pass


class AIInvalidOutputError(AIError):
    """Raised when the model output is not valid JSON or cannot be parsed."""
    pass


class AISchemaValidationError(AIError):
    """Raised when the model output fails Pydantic schema validation."""
    pass


class AIGenerationLimitError(AIError):
    """Raised when generated items exceed configured boundaries."""
    pass


class AIProvider(ABC):
    """Abstract interface for local/offline AI model providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_schema: type[BaseModel] | None = None,
        timeout: float | None = None,
    ) -> str | dict[str, Any]:
        """Generate unstructured text or structured JSON from the model.
        
        Args:
            prompt: The user-level input prompt (untrusted repository data clearly demarcated).
            system_prompt: High-priority system instructions controlling output schema and constraints.
            response_schema: Optional Pydantic model for structured output validation.
            timeout: Optional per-request timeout in seconds.
            
        Returns:
            String response if response_schema is None, or parsed dictionary if response_schema is provided.
            
        Raises:
            AIUnavailableError: If provider service is unreachable.
            AITimeoutError: If generation takes longer than allowed.
            AIInvalidOutputError: If output is not valid JSON when schema is requested.
            AISchemaValidationError: If output does not conform to response_schema.
            AIError: For any other provider-level failures.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the local AI service is reachable and responding."""
        ...

    async def preflight(self) -> dict[str, Any]:
        """Perform preflight checks: verify service, model existence, and warm-up.
        Returns:
            Dict containing status ("READY" | "WARMING" | "UNAVAILABLE" | "ERROR"),
            ready boolean, model name, and diagnostic message.
        """
        available = await self.is_available()
        return {
            "status": "READY" if available else "UNAVAILABLE",
            "ready": available,
            "message": "AI service is available" if available else "AI service is unavailable",
        }
