"""Pure evaluation metrics.

Retrieval metrics are judged against an expected document (and optionally a
page); answer metrics against expected keywords and the citation set. All
functions are deterministic and side-effect free.
"""

from __future__ import annotations

from typing import Any


def reciprocal_rank(ranked_document_ids: list[str], expected_document_id: str) -> float:
    """1/rank of the first hit; 0.0 when the expected document never appears."""
    for position, document_id in enumerate(ranked_document_ids, start=1):
        if document_id == expected_document_id:
            return 1.0 / position
    return 0.0


def page_hit(
    ranked: list[tuple[str, int | None]],
    expected_document_id: str,
    expected_page: int,
) -> bool:
    """True when a result cites the expected document at the expected page."""
    return any(
        document_id == expected_document_id and page == expected_page
        for document_id, page in ranked
    )


def keyword_recall(answer: str | None, keywords: list[str]) -> float:
    """Fraction of expected keywords present in the answer (case-insensitive)."""
    if not keywords:
        return 0.0
    if not answer:
        return 0.0
    haystack = answer.lower()
    found = sum(1 for keyword in keywords if keyword.lower() in haystack)
    return found / len(keywords)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold per-case results into run-level metrics.

    Each metric averages only the cases that could be judged for it (e.g.
    cases without an expected document don't dilute retrieval metrics).
    ``None`` means no case was judgeable for that metric.
    """
    retrieval = [r for r in results if r.get("reciprocal_rank") is not None]
    paged = [r for r in results if r.get("page_hit") is not None]
    keyworded = [r for r in results if r.get("keyword_recall") is not None]
    cited = [r for r in results if r.get("citation_hit") is not None]
    answered = [r for r in results if r.get("answered") is not None]

    return {
        "cases": len(results),
        "hit_rate": _mean([1.0 if r["reciprocal_rank"] > 0 else 0.0 for r in retrieval]),
        "mrr": _mean([r["reciprocal_rank"] for r in retrieval]),
        "page_hit_rate": _mean([1.0 if r["page_hit"] else 0.0 for r in paged]),
        "answered_rate": _mean([1.0 if r["answered"] else 0.0 for r in answered]),
        "citation_accuracy": _mean([1.0 if r["citation_hit"] else 0.0 for r in cited]),
        "keyword_recall": _mean([r["keyword_recall"] for r in keyworded]),
        "avg_confidence": _mean(
            [r["confidence"] for r in results if r.get("confidence") is not None]
        ),
        "avg_grounded_ratio": _mean(
            [r["grounded_ratio"] for r in results if r.get("grounded_ratio") is not None]
        ),
    }
