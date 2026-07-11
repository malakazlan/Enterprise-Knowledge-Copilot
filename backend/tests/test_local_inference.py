"""Tests for local ONNX inference (fastembed): embedder + cross-encoder.

Skipped when the [local] extra is not installed (e.g. CI); run locally where
the models are cached. These exercise REAL model inference — the point is to
verify semantic behaviour, not just plumbing.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("fastembed")

from app.services.ingestion.embedding import FastEmbedEmbedder
from app.services.retrieval.rerank import OnnxCrossEncoderReranker
from app.services.retrieval.types import RetrievedChunk


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def _chunk(chunk_id: str, content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="d1",
        filename="f.md",
        title=None,
        page_number=1,
        chunk_index=0,
        content=content,
        fused_score=1.0,
    )


@pytest.fixture(scope="module")
def embedder() -> FastEmbedEmbedder:
    return FastEmbedEmbedder(model="BAAI/bge-small-en-v1.5")


async def test_embeddings_are_semantic(embedder: FastEmbedEmbedder) -> None:
    assert embedder.dimension == 384
    vectors = await embedder.embed(
        [
            "All workers must wear a helmet on the construction site.",
            "Hard hats are required protective equipment for staff.",
            "Quarterly revenue projections exceeded expectations.",
        ]
    )
    assert all(len(v) == 384 for v in vectors)
    related = _cosine(vectors[0], vectors[1])
    unrelated = _cosine(vectors[0], vectors[2])
    # Paraphrases must land meaningfully closer than off-topic text.
    assert related > unrelated + 0.1, (related, unrelated)


async def test_query_embedding_matches_dimension(embedder: FastEmbedEmbedder) -> None:
    query_vector = await embedder.embed_query("What safety gear is required?")
    assert len(query_vector) == embedder.dimension
    (passage_vector,) = await embedder.embed(["Helmets and high-visibility vests are mandatory."])
    assert _cosine(query_vector, passage_vector) > 0.5


async def test_cross_encoder_ranks_relevant_first() -> None:
    reranker = OnnxCrossEncoderReranker(model="Xenova/ms-marco-MiniLM-L-6-v2")
    candidates = [
        _chunk("cafeteria", "The cafeteria serves lunch between noon and 2 pm."),
        _chunk("helmet", "All personnel must wear an approved safety helmet on site."),
        _chunk("parking", "Visitor parking is available behind building B."),
    ]
    top = await reranker.rerank("Who must wear a helmet?", candidates, top_n=2)
    assert top[0].chunk_id == "helmet"
    assert len(top) == 2
    assert top[0].rerank_score is not None and top[0].rerank_score > top[1].rerank_score


async def test_unsupported_model_is_rejected() -> None:
    from app.core.exceptions import ServiceUnavailableError

    with pytest.raises(ServiceUnavailableError, match="does not support"):
        FastEmbedEmbedder(model="not/a-real-model")
