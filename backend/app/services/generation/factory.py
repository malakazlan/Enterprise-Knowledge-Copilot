"""Answer-generator factory resolved from settings.

Every LLM-backed provider is wrapped in :class:`LLMCitationGenerator`, so all
of them share identical grounding, citation parsing, and refusal behavior.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.services.generation.extractive import ExtractiveGenerator
from app.services.generation.llm_generator import LLMCitationGenerator
from app.services.generation.ports import AnswerGenerator, LLMProvider
from app.services.generation.providers import AnthropicProvider, OpenAICompatibleProvider


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    """The raw configured LLM, or None on the extractive (no-LLM) tier."""
    provider = settings.llm_provider

    if provider == "extractive":
        return None

    if provider == "anthropic":
        api_key = settings.anthropic_api_key
        return AnthropicProvider(
            api_key=api_key.get_secret_value() if api_key else None,
            model=settings.anthropic_model,
        )

    if provider == "openai":
        api_key = settings.openai_api_key
        if api_key is None:
            raise ServiceUnavailableError("OPENAI_API_KEY is required when llm_provider=openai.")
        return OpenAICompatibleProvider(
            api_key=api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )

    if provider == "ollama":
        # Ollama's OpenAI-compatible endpoint ignores the key but requires one.
        return OpenAICompatibleProvider(
            api_key="ollama",
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            provider_label="ollama",
        )

    raise ServiceUnavailableError(f"LLM provider '{provider}' is not configured.")


@lru_cache
def get_answer_generator() -> AnswerGenerator:
    llm = get_llm_provider()
    if llm is None:
        return ExtractiveGenerator()
    return LLMCitationGenerator(llm)
