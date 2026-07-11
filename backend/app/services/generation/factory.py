"""Answer-generator factory resolved from settings."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.services.generation.extractive import ExtractiveGenerator
from app.services.generation.ports import AnswerGenerator


@lru_cache
def get_answer_generator() -> AnswerGenerator:
    provider = settings.llm_provider
    if provider == "extractive":
        return ExtractiveGenerator()
    # LLM adapters (anthropic/openai/ollama) plug in here via LLMCitationGenerator.
    raise ServiceUnavailableError(f"LLM provider '{provider}' is not configured.")
