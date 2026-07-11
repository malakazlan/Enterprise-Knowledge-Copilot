"""Extractive answer generator — the zero-dependency offline default.

Selects the sentences most relevant to the query from the retrieved chunks
(BM25 over the sentence pool) and composes them verbatim with citations.
Answers are grounded *by construction* — every sentence is a quote from a
source. It has no reasoning ability; deployments wanting synthesized answers
configure an LLM provider, which replaces this via one config line.

Two quality gates keep the fallback honest on messy real-world corpora:

- **Sentence quality floor** — fragments with fewer than a handful of
  meaning-bearing tokens (layout debris, one-word lines) are never quoted.
- **Content-token overlap** — a sentence must share at least one
  non-stopword token with the question; matching only on function words
  ("what", "is", "how") yields a refusal instead of a confident non-answer.
"""

from __future__ import annotations

from app.services.generation.ports import DraftAnswer, DraftCitation
from app.services.generation.sentences import content_tokens, split_sentences
from app.services.profiles.schema import RagProfile
from app.services.retrieval.bm25 import BM25Index
from app.services.retrieval.tokenize import tokenize
from app.services.retrieval.types import RetrievedChunk

_MAX_SENTENCES = 3
# Sentences with fewer meaning-bearing tokens are layout debris, not answers.
_MIN_SENTENCE_CONTENT_TOKENS = 4


class ExtractiveGenerator:
    name = "extractive-v1"

    async def generate(
        self, query: str, chunks: list[RetrievedChunk], profile: RagProfile
    ) -> DraftAnswer:
        if not chunks:
            return DraftAnswer(text=None, model=self.name)

        query_content = content_tokens(query)

        # Index every acceptable sentence; the ID encodes its origin.
        sentence_pool: list[tuple[str, str]] = []  # (sentence_id, sentence)
        origin: dict[str, tuple[int, int, str]] = {}  # id -> (chunk pos, sent pos, text)
        for chunk_position, chunk in enumerate(chunks, start=1):
            for sentence_position, sentence in enumerate(split_sentences(chunk.content)):
                sentence_content = content_tokens(sentence)
                if len(sentence_content) < _MIN_SENTENCE_CONTENT_TOKENS:
                    continue  # layout fragment, not a quotable sentence
                if query_content and not (sentence_content & query_content):
                    continue  # only function words matched -> not evidence
                sentence_id = f"{chunk_position}:{sentence_position}"
                sentence_pool.append((sentence_id, sentence))
                origin[sentence_id] = (chunk_position, sentence_position, sentence)

        if not sentence_pool:
            return DraftAnswer(text=None, model=self.name)

        index = BM25Index()
        index.build([(sid, tokenize(sentence)) for sid, sentence in sentence_pool])
        hits = index.search(tokenize(query), top_k=_MAX_SENTENCES)
        relevant = [sid for sid, score in hits if score > 0.0]
        if not relevant:
            return DraftAnswer(text=None, model=self.name)

        # Compose in document order for readability; markers reference chunks.
        selected = sorted(origin[sid] for sid in relevant)
        parts: list[str] = []
        used_markers: list[int] = []
        for chunk_position, _, sentence in selected:
            body = sentence.rstrip(".!?")
            parts.append(f"{body} [{chunk_position}].")
            if chunk_position not in used_markers:
                used_markers.append(chunk_position)

        citations = [
            DraftCitation(marker=marker, chunk=chunks[marker - 1]) for marker in used_markers
        ]
        return DraftAnswer(
            text=" ".join(parts),
            citations=citations,
            model=self.name,
            total_markers=len(selected),
            invalid_markers=0,
        )
