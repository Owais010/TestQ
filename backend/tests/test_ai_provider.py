"""Tests for Phase 4 AI Provider abstraction and local Ollama client."""
import json
import pytest
import httpx
from pydantic import BaseModel, Field

from app.ai.base import (
    AIError,
    AIUnavailableError,
    AITimeoutError,
    AIInvalidOutputError,
    AISchemaValidationError,
    AIGenerationLimitError,
)
from app.ai.ollama import OllamaProvider
from app.ai.factory import get_ai_provider


class SampleSchema(BaseModel):
    name: str = Field(min_length=2)
    score: int = Field(ge=0, le=100)


@pytest.mark.asyncio
async def test_ollama_provider_configuration():
    provider = OllamaProvider(
        host="http://custom-ollama:11434",
        model="custom-model:8b",
        timeout=30.0,
        max_output_bytes=100000,
    )
    assert provider.host == "http://custom-ollama:11434"
    assert provider.model == "custom-model:8b"
    assert provider.timeout == 30.0
    assert provider.max_output_bytes == 100000


@pytest.mark.asyncio
async def test_factory_returns_ollama():
    prov = get_ai_provider()
    assert isinstance(prov, OllamaProvider)


@pytest.mark.asyncio
async def test_ollama_provider_valid_text_generation(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model")

    async def mock_post(self, url, json=None, **kwargs):
        assert url == "http://test-host:11434/api/generate"
        assert json["model"] == "test-model"
        assert json["prompt"] == "Hello"
        return httpx.Response(200, json={"response": "Hello from model", "done": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await provider.generate("Hello")
    assert result == "Hello from model"


@pytest.mark.asyncio
async def test_ollama_provider_valid_structured_json(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model")

    async def mock_post(self, url, json=None, **kwargs):
        assert json.get("format") == "json"
        return httpx.Response(
            200,
            json={"response": '{"name": "Alpha", "score": 95}', "done": True},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await provider.generate("Score Alpha", response_schema=SampleSchema)
    assert isinstance(result, dict)
    assert result["name"] == "Alpha"
    assert result["score"] == 95


@pytest.mark.asyncio
async def test_ollama_provider_strips_markdown_code_fences(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model")

    fenced_output = """```json
{
  "name": "Beta",
  "score": 88
}
```"""

    async def mock_post(self, url, json=None, **kwargs):
        return httpx.Response(200, json={"response": fenced_output, "done": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await provider.generate("Test fences", response_schema=SampleSchema)
    assert result["name"] == "Beta"
    assert result["score"] == 88


@pytest.mark.asyncio
async def test_ollama_provider_unavailable(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model")

    async def mock_post(self, url, **kwargs):
        raise httpx.ConnectError("Connection refused by test-host")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(AIUnavailableError) as exc_info:
        await provider.generate("Hello")
    assert "unavailable" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ollama_provider_timeout(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model", timeout=2.0)

    async def mock_post(self, url, **kwargs):
        raise httpx.ReadTimeout("Read timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(AITimeoutError) as exc_info:
        await provider.generate("Hello")
    assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ollama_provider_malformed_json(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model")

    async def mock_post(self, url, **kwargs):
        return httpx.Response(200, json={"response": "{not a valid json}", "done": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(AIInvalidOutputError) as exc_info:
        await provider.generate("Hello", response_schema=SampleSchema)
    assert "not valid json" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ollama_provider_schema_validation_failure(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model")

    # Score exceeds 100 limit in SampleSchema
    async def mock_post(self, url, **kwargs):
        return httpx.Response(200, json={"response": '{"name": "Gamma", "score": 999}', "done": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(AISchemaValidationError) as exc_info:
        await provider.generate("Hello", response_schema=SampleSchema)
    assert "schema validation" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ollama_provider_output_limit_exceeded(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434", model="test-model", max_output_bytes=50)

    async def mock_post(self, url, **kwargs):
        return httpx.Response(200, json={"response": "A" * 100, "done": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(AIGenerationLimitError) as exc_info:
        await provider.generate("Hello")
    assert "limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ollama_provider_is_available_check(monkeypatch):
    provider = OllamaProvider(host="http://test-host:11434")

    async def mock_get(self, url, **kwargs):
        if "healthy" in url:
            return httpx.Response(200, json={"models": []})
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    provider.host = "http://healthy:11434"
    assert await provider.is_available() is True

    provider.host = "http://offline:11434"
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_ai_provider_has_no_execution_privileges():
    """Verify that OllamaProvider has no subprocess, system shell, or eval privileges."""
    provider = OllamaProvider()
    assert not hasattr(provider, "execute")
    assert not hasattr(provider, "run_shell")
    assert not hasattr(provider, "evaluate")
    assert not hasattr(provider, "docker_client")
