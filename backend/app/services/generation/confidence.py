"""Composite answer confidence — transparent and deterministic.

Three components, each in [0, 1], combined with fixed weights:

- ``retrieval``    — strength of the best fused evidence. RRF scores live in
  (0, C/(k+1)] for C channels, so the top score is normalized against the
  two-channel maximum ``2/(k+1)``: 1.0 means both channels ranked the same
  chunk first.
- ``groundedness`` — fraction of scoreable answer sentences supported by
  their cited sources.
- ``citations``    — marker discipline: share of citation markers that were
  valid. No markers at all scores 0 when the profile requires citations.

The breakdown ships in every API response — a confidence number no one can
inspect is a number no one should trust.
"""

from __future__ import annotations

WEIGHT_RETRIEVAL = 0.35
WEIGHT_GROUNDEDNESS = 0.40
WEIGHT_CITATIONS = 0.25


def compute_confidence(
    *,
    top_fused_score: float,
    rrf_k: int,
    grounded_ratio: float,
    total_markers: int,
    invalid_markers: int,
    citations_required: bool,
) -> tuple[float, dict[str, float]]:
    max_fused = 2.0 / (rrf_k + 1)
    retrieval = min(max(top_fused_score / max_fused, 0.0), 1.0) if max_fused > 0 else 0.0

    if total_markers > 0:
        citations = (total_markers - invalid_markers) / total_markers
    else:
        citations = 0.0 if citations_required else 1.0

    groundedness = min(max(grounded_ratio, 0.0), 1.0)

    overall = (
        WEIGHT_RETRIEVAL * retrieval
        + WEIGHT_GROUNDEDNESS * groundedness
        + WEIGHT_CITATIONS * citations
    )
    breakdown = {
        "retrieval": round(retrieval, 4),
        "groundedness": round(groundedness, 4),
        "citations": round(citations, 4),
    }
    return round(overall, 4), breakdown
