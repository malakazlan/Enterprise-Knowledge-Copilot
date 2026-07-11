"""Unit tests for the pure BM25 index and RRF fusion."""

from __future__ import annotations

import pytest

from app.services.retrieval.bm25 import BM25Index
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.tokenize import tokenize


def _index(docs: dict[str, str]) -> BM25Index:
    index = BM25Index()
    index.build([(doc_id, tokenize(text)) for doc_id, text in docs.items()])
    return index


# --- BM25 ---


def test_exact_term_match_ranks_first() -> None:
    index = _index(
        {
            "a": "workers must wear a helmet on the construction site",
            "b": "the cafeteria menu changes every week",
            "c": "invoices are processed by the finance department",
        }
    )
    results = index.search(tokenize("helmet"), top_k=3)
    assert results
    assert results[0][0] == "a"
    assert results[0][1] > 0.0


def test_rare_terms_outweigh_common_terms() -> None:
    # "policy" appears everywhere (low IDF); "asbestos" only in one doc.
    index = _index(
        {
            "a": "company policy on remote work and travel policy",
            "b": "company policy for expense reports policy",
            "c": "company policy on asbestos handling",
        }
    )
    results = index.search(tokenize("policy asbestos"), top_k=3)
    assert results[0][0] == "c"


def test_allowed_ids_filters_without_changing_stats() -> None:
    index = _index(
        {
            "a": "helmet safety rules",
            "b": "helmet inspection checklist",
            "c": "unrelated cafeteria menu",
        }
    )
    results = index.search(tokenize("helmet"), top_k=5, allowed_ids={"b"})
    assert [doc_id for doc_id, _ in results] == ["b"]


def test_no_match_and_empty_inputs() -> None:
    index = _index({"a": "some content"})
    assert index.search(tokenize("zzz missing"), top_k=5) == []
    assert index.search([], top_k=5) == []
    empty = BM25Index()
    assert empty.search(tokenize("anything"), top_k=5) == []


def test_top_k_limits_results() -> None:
    index = _index({f"d{i}": "shared token here" for i in range(10)})
    assert len(index.search(tokenize("shared"), top_k=3)) == 3


def test_tokenizer_keeps_numbers() -> None:
    assert tokenize("Error E-4711 on part 99-B.") == ["error", "e", "4711", "on", "part", "99", "b"]


# --- RRF ---


def test_rrf_rewards_cross_channel_agreement() -> None:
    fused = reciprocal_rank_fusion([["x", "y"], ["x", "z"]], k=60)
    assert fused["x"] == pytest.approx(2 / 61)
    assert fused["y"] == pytest.approx(1 / 62)
    assert fused["x"] > fused["y"]
    assert fused["x"] > fused["z"]


def test_rrf_rank_positions_matter() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
    assert fused["a"] > fused["b"] > fused["c"]


def test_rrf_rejects_invalid_k() -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=0)
