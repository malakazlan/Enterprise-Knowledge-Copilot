"""Reciprocal Rank Fusion (RRF) for combining retrieval channels.

RRF fuses ranked lists using only rank positions, which makes it robust to the
incomparable score scales of dense (cosine) and sparse (BM25) channels:

    score(d) = sum over channels of 1 / (k + rank_of_d_in_channel)

The constant ``k`` dampens the dominance of top positions; 60 is the standard
value from the original Cormack et al. paper and works well in practice.
"""

from __future__ import annotations

from collections.abc import Sequence


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], *, k: int = 60) -> dict[str, float]:
    """Fuse ranked ID lists into ``{id: fused_score}``.

    Items appearing in multiple channels accumulate score from each, so
    cross-channel agreement is rewarded.
    """
    if k < 1:
        raise ValueError("k must be >= 1.")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores
