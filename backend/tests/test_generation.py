"""Unit tests for generation building blocks."""

from __future__ import annotations

import pytest

from app.services.generation.confidence import compute_confidence
from app.services.generation.extractive import ExtractiveGenerator
from app.services.generation.groundedness import check_groundedness
from app.services.generation.llm_generator import LLMCitationGenerator
from app.services.generation.ports import (
    INSUFFICIENT_EVIDENCE,
    CompletionRequest,
    CompletionResult,
)
from app.services.generation.sentences import sentence_markers, split_sentences
from app.services.profiles.loader import get_profile
from app.services.retrieval.types import RetrievedChunk


def _chunk(chunk_id: str, content: str, *, page: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="d1",
        filename="doc.md",
        title="Doc",
        page_number=page,
        chunk_index=0,
        content=content,
        fused_score=0.03,
    )


SAFETY = _chunk(
    "c1",
    "All workers must wear a helmet at all times on the construction site. "
    "Helmets are inspected monthly by the safety officer.",
)
FINANCE = _chunk("c2", "Invoices must be submitted before the 5th of each month.", page=2)


# --- sentences ---


def test_split_sentences_merges_trailing_markers() -> None:
    parts = split_sentences("Workers wear helmets. [1] Fire drills happen monthly. [2]")
    assert parts == ["Workers wear helmets. [1]", "Fire drills happen monthly. [2]"]


def test_sentence_markers_extraction() -> None:
    assert sentence_markers("Helmets required [1][3].") == [1, 3]


# --- extractive generator ---


async def test_extractive_answers_with_valid_citations() -> None:
    draft = await ExtractiveGenerator().generate(
        "who must wear a helmet?", [SAFETY, FINANCE], get_profile("general")
    )
    assert draft.text is not None
    assert "helmet" in draft.text.lower()
    assert "[1]" in draft.text
    assert draft.citations and draft.citations[0].marker == 1
    assert draft.citations[0].chunk.chunk_id == "c1"
    assert draft.invalid_markers == 0


async def test_extractive_returns_insufficient_for_irrelevant_query() -> None:
    draft = await ExtractiveGenerator().generate(
        "quantum banana smoothie recipe", [SAFETY], get_profile("general")
    )
    assert draft.text is None


async def test_extractive_with_no_chunks() -> None:
    draft = await ExtractiveGenerator().generate("anything", [], get_profile("general"))
    assert draft.text is None


# --- LLM citation generator (via fake provider) ---


class FakeLLM:
    name = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_request: CompletionRequest | None = None

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.last_request = request
        return CompletionResult(text=self.reply)


async def test_llm_generator_parses_valid_markers() -> None:
    fake = FakeLLM("Workers must wear helmets on site [1]. Invoices are due by the 5th [2].")
    draft = await LLMCitationGenerator(fake).generate(
        "rules?", [SAFETY, FINANCE], get_profile("general")
    )
    assert draft.text is not None
    assert [citation.marker for citation in draft.citations] == [1, 2]
    assert draft.total_markers == 2
    assert draft.invalid_markers == 0
    # The provider received numbered sources and the grounding rules.
    assert fake.last_request is not None
    assert "[1]" in fake.last_request.user
    assert INSUFFICIENT_EVIDENCE in fake.last_request.system


async def test_llm_generator_counts_invalid_markers() -> None:
    fake = FakeLLM("Helmets are required [1]. This is fabricated [7].")
    draft = await LLMCitationGenerator(fake).generate(
        "rules?", [SAFETY, FINANCE], get_profile("general")
    )
    assert draft.total_markers == 2
    assert draft.invalid_markers == 1
    assert [citation.marker for citation in draft.citations] == [1]


async def test_llm_generator_maps_sentinel_to_refusal() -> None:
    fake = FakeLLM(INSUFFICIENT_EVIDENCE)
    draft = await LLMCitationGenerator(fake).generate("rules?", [SAFETY], get_profile("general"))
    assert draft.text is None


# --- groundedness ---


def test_grounded_sentence_passes() -> None:
    text = "All workers must wear a helmet on the construction site [1]."
    report = check_groundedness(text, {1: SAFETY})
    assert report.total_sentences == 1
    assert report.grounded_sentences == 1
    assert report.ratio == 1.0


def test_fabricated_sentence_fails() -> None:
    text = "Employees receive quarterly stock bonuses and a company yacht [1]."
    report = check_groundedness(text, {1: SAFETY})
    assert report.total_sentences == 1
    assert report.grounded_sentences == 0


def test_uncited_factual_sentence_counts_as_ungrounded() -> None:
    text = "All workers must wear a helmet on the construction site."
    report = check_groundedness(text, {1: SAFETY})
    assert report.total_sentences == 1
    assert report.grounded_sentences == 0


# --- confidence ---


def test_confidence_composition_and_bounds() -> None:
    confidence, breakdown = compute_confidence(
        top_fused_score=2.0 / 61,  # both channels rank-1 with k=60 -> retrieval 1.0
        rrf_k=60,
        grounded_ratio=1.0,
        total_markers=3,
        invalid_markers=0,
        citations_required=True,
    )
    assert breakdown == {"retrieval": 1.0, "groundedness": 1.0, "citations": 1.0}
    assert confidence == pytest.approx(1.0)


def test_confidence_penalizes_missing_required_citations() -> None:
    confidence, breakdown = compute_confidence(
        top_fused_score=2.0 / 61,
        rrf_k=60,
        grounded_ratio=1.0,
        total_markers=0,
        invalid_markers=0,
        citations_required=True,
    )
    assert breakdown["citations"] == 0.0
    assert confidence == pytest.approx(0.75)
