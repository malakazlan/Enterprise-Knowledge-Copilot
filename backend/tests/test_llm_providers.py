"""Adapter tests for the Anthropic and OpenAI-compatible LLM providers.

The real SDKs run end-to-end against a mocked HTTP transport, verifying the
exact wire request each adapter constructs and how it parses responses —
without needing live API keys.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.exceptions import ServiceUnavailableError
from app.services.generation.ports import CompletionRequest
from app.services.generation.providers import AnthropicProvider, OpenAICompatibleProvider

REQUEST = CompletionRequest(
    system="You are grounded.", user="Question?", temperature=0.0, max_tokens=1234
)


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _anthropic_message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-8",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _openai_completion(text: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


# --- Anthropic ---


async def test_anthropic_request_shape_and_parsing() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["api_key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json=_anthropic_message("Helmets required [1]."))

    provider = AnthropicProvider(
        api_key="test-key", model="claude-opus-4-8", http_client=_client(handler)
    )
    result = await provider.complete(REQUEST)

    assert result.text == "Helmets required [1]."
    assert provider.name == "anthropic:claude-opus-4-8"
    assert captured["path"] == "/v1/messages"
    assert captured["api_key"] == "test-key"

    body = captured["body"]
    assert body["model"] == "claude-opus-4-8"
    assert body["system"] == "You are grounded."
    assert body["messages"] == [{"role": "user", "content": "Question?"}]
    assert body["max_tokens"] == 1234
    # Sampling params are removed on current Claude models (400 if sent).
    assert "temperature" not in body


async def test_anthropic_refusal_maps_to_empty_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_anthropic_message("", stop_reason="refusal"))

    provider = AnthropicProvider(api_key="k", model="claude-opus-4-8", http_client=_client(handler))
    result = await provider.complete(REQUEST)
    assert result.text == ""


async def test_anthropic_api_error_becomes_503() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"type": "error", "error": {"type": "authentication_error", "message": "bad key"}},
        )

    provider = AnthropicProvider(api_key="k", model="claude-opus-4-8", http_client=_client(handler))
    with pytest.raises(ServiceUnavailableError):
        await provider.complete(REQUEST)


# --- OpenAI-compatible ---


async def test_openai_request_shape_and_parsing() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_openai_completion("Invoices are due [2]."))

    provider = OpenAICompatibleProvider(
        api_key="sk-test", base_url=None, model="gpt-4o-mini", http_client=_client(handler)
    )
    result = await provider.complete(REQUEST)

    assert result.text == "Invoices are due [2]."
    assert provider.name == "openai:gpt-4o-mini"
    assert captured["auth"] == "Bearer sk-test"

    body = captured["body"]
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"][0] == {"role": "system", "content": "You are grounded."}
    assert body["messages"][1] == {"role": "user", "content": "Question?"}
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 1234


async def test_openai_base_url_override_reaches_local_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_openai_completion("local answer [1]."))

    provider = OpenAICompatibleProvider(
        api_key="ollama",
        base_url="http://localhost:11434/v1",
        model="llama3.1",
        provider_label="ollama",
        http_client=_client(handler),
    )
    result = await provider.complete(REQUEST)

    assert result.text == "local answer [1]."
    assert provider.name == "ollama:llama3.1"
    assert captured["url"].startswith("http://localhost:11434/v1/")


async def test_openai_error_becomes_503() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom", "type": "server_error"}})

    provider = OpenAICompatibleProvider(
        api_key="sk-test", base_url=None, model="gpt-4o-mini", http_client=_client(handler)
    )
    with pytest.raises(ServiceUnavailableError):
        await provider.complete(REQUEST)
