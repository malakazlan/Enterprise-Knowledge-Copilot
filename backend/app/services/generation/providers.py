"""LLM provider adapters implementing the :class:`LLMProvider` port.

- :class:`AnthropicProvider` — official ``anthropic`` SDK (verified against
  0.116). Current Claude models (Opus 4.7+) reject sampling parameters, so the
  profile's ``temperature`` is intentionally not forwarded — determinism comes
  from the grounded prompt. A safety ``refusal`` stop reason maps to empty
  text, which the citation generator treats as insufficient evidence.
- :class:`OpenAICompatibleProvider` — official ``openai`` SDK (verified
  against 2.45) with a configurable ``base_url``; one adapter covers OpenAI,
  Ollama, vLLM, and LM Studio.

Provider failures raise :class:`ServiceUnavailableError` so the API returns a
clean 503 instead of an opaque 500.
"""

from __future__ import annotations

import anthropic
import httpx
import openai

from app.core.exceptions import ServiceUnavailableError
from app.services.generation.ports import CompletionRequest, CompletionResult


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        # Without an explicit key the SDK resolves credentials from the
        # environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
        if api_key is not None:
            self._client = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)
        else:
            self._client = anthropic.AsyncAnthropic(http_client=http_client)
        self.model = model
        self.name = f"anthropic:{model}"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            message = await self._client.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
            )
        except anthropic.APIError as exc:
            raise ServiceUnavailableError(f"Anthropic API error: {exc}") from exc

        # Safety classifiers can decline a request (HTTP 200, stop_reason
        # "refusal") — surface it as an empty completion, never as an answer.
        if message.stop_reason == "refusal":
            return CompletionResult(text="")

        text = "".join(block.text for block in message.content if block.type == "text")
        return CompletionResult(text=text)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model: str,
        provider_label: str = "openai",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, http_client=http_client
        )
        self.model = model
        self.name = f"{provider_label}:{model}"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except openai.OpenAIError as exc:
            raise ServiceUnavailableError(f"LLM provider error: {exc}") from exc

        text = response.choices[0].message.content if response.choices else None
        return CompletionResult(text=text or "")
