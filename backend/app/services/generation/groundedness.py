"""Lexical groundedness check: is each answer sentence supported by its cited sources?

For every scoreable sentence, the check computes content-token overlap between
the sentence and the union of the chunks it cites. A sentence with no citation
markers, or with overlap below the support threshold, counts as ungrounded.

This is a deterministic lexical proxy — strict for extractive/quoting answers
and a useful tripwire for paraphrasing LLMs. An NLI/LLM-judge implementation
can replace it behind the same function signature when cloud providers land.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.generation.sentences import (
    content_tokens,
    sentence_markers,
    split_sentences,
    strip_markers,
)
from app.services.retrieval.types import RetrievedChunk

# A sentence is "supported" when at least this fraction of its content tokens
# appears in the union of its cited chunks.
SUPPORT_THRESHOLD = 0.5
# Sentences with fewer content tokens are connective glue; they are skipped
# rather than counted for or against groundedness.
MIN_CONTENT_TOKENS = 4


@dataclass(slots=True)
class GroundednessReport:
    total_sentences: int
    grounded_sentences: int

    @property
    def ratio(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return self.grounded_sentences / self.total_sentences


def check_groundedness(text: str, marker_map: dict[int, RetrievedChunk]) -> GroundednessReport:
    chunk_token_cache: dict[int, set[str]] = {}

    def tokens_for(markers: list[int]) -> set[str]:
        union: set[str] = set()
        for marker in markers:
            chunk = marker_map.get(marker)
            if chunk is None:
                continue
            if marker not in chunk_token_cache:
                chunk_token_cache[marker] = content_tokens(chunk.content)
            union |= chunk_token_cache[marker]
        return union

    total = 0
    grounded = 0
    for sentence in split_sentences(text):
        sentence_content = content_tokens(strip_markers(sentence))
        if len(sentence_content) < MIN_CONTENT_TOKENS:
            continue
        total += 1

        markers = sentence_markers(sentence)
        if not markers:
            continue  # uncited factual sentence -> ungrounded
        support = tokens_for(markers)
        if not support:
            continue
        overlap = len(sentence_content & support) / len(sentence_content)
        if overlap >= SUPPORT_THRESHOLD:
            grounded += 1

    return GroundednessReport(total_sentences=total, grounded_sentences=grounded)
