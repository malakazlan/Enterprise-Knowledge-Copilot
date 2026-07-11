"""Wraps any :class:`LLMProvider` with the grounded citation protocol.

The provider only completes text; this class owns the prompt, the
``INSUFFICIENT_EVIDENCE`` sentinel, and ``[n]`` marker parsing/validation —
so every LLM adapter (Anthropic, OpenAI, Ollama) gets identical citation
behavior for free.
"""

from __future__ import annotations

import re

from app.services.generation.ports import (
    INSUFFICIENT_EVIDENCE,
    CompletionRequest,
    DraftAnswer,
    DraftCitation,
    LLMProvider,
)
from app.services.generation.prompting import build_system_prompt, build_user_prompt
from app.services.profiles.schema import RagProfile
from app.services.retrieval.types import RetrievedChunk

_MARKER_RE = re.compile(r"\[(\d+)\]")


class LLMCitationGenerator:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.name = f"llm:{provider.name}"

    async def generate(
        self, query: str, chunks: list[RetrievedChunk], profile: RagProfile
    ) -> DraftAnswer:
        if not chunks:
            return DraftAnswer(text=None, model=self.name)

        result = await self.provider.complete(
            CompletionRequest(
                system=build_system_prompt(profile),
                user=build_user_prompt(query, chunks),
                temperature=profile.generation.temperature,
                max_tokens=profile.generation.max_tokens,
            )
        )
        text = result.text.strip()

        # The sentinel may arrive with whitespace or minor decoration around it.
        if not text or INSUFFICIENT_EVIDENCE in text[:80]:
            return DraftAnswer(text=None, model=self.name)

        markers = [int(match) for match in _MARKER_RE.findall(text)]
        valid_range = range(1, len(chunks) + 1)
        seen: list[int] = []
        invalid = 0
        for marker in markers:
            if marker not in valid_range:
                invalid += 1
            elif marker not in seen:
                seen.append(marker)

        citations = [DraftCitation(marker=marker, chunk=chunks[marker - 1]) for marker in seen]
        return DraftAnswer(
            text=text,
            citations=citations,
            model=self.name,
            total_markers=len(markers),
            invalid_markers=invalid,
        )
