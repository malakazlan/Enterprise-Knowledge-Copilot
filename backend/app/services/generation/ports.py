"""Ports and value objects for grounded answer generation.

Two levels of abstraction:

- :class:`LLMProvider` — raw text-in/text-out completion. Cloud and local
  model adapters (Anthropic, OpenAI, Ollama/vLLM) implement this.
- :class:`AnswerGenerator` — (query, evidence chunks, profile) -> draft answer
  with citations. ``ExtractiveGenerator`` implements it offline;
  ``LLMCitationGenerator`` wraps any :class:`LLMProvider` with the grounded
  citation prompt and marker parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.services.profiles.schema import RagProfile
from app.services.retrieval.types import RetrievedChunk

# Sentinel a generator returns (or an LLM is instructed to emit) when the
# provided sources do not contain the answer. Deterministic protocol beats
# fuzzy "I don't know" detection.
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(slots=True)
class CompletionRequest:
    system: str
    user: str
    temperature: float
    max_tokens: int


@dataclass(slots=True)
class CompletionResult:
    text: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...


@dataclass(slots=True)
class DraftCitation:
    marker: int  # 1-based index into the evidence list, as used in the answer
    chunk: RetrievedChunk


@dataclass(slots=True)
class DraftAnswer:
    """Generator output before policy (groundedness/confidence/thresholds)."""

    text: str | None  # None -> generator judged the evidence insufficient
    citations: list[DraftCitation] = field(default_factory=list)
    model: str = ""
    total_markers: int = 0
    invalid_markers: int = 0

    def marker_map(self) -> dict[int, RetrievedChunk]:
        return {citation.marker: citation.chunk for citation in self.citations}


@runtime_checkable
class AnswerGenerator(Protocol):
    name: str

    async def generate(
        self, query: str, chunks: list[RetrievedChunk], profile: RagProfile
    ) -> DraftAnswer: ...
