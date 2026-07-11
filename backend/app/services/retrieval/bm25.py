"""Pure Okapi BM25 index — dependency-free and deterministic.

Serves as the default sparse retrieval channel and as the scoring core of the
lexical reranker. Uses posting lists, so query cost scales with the document
frequency of the query terms rather than corpus size. Production-scale sparse
backends (e.g. a search engine) implement the same search contract behind the
sparse-index port.
"""

from __future__ import annotations

from collections import Counter
from math import log

DEFAULT_K1 = 1.5
DEFAULT_B = 0.75


class BM25Index:
    """Okapi BM25 over a tokenized corpus.

    The IDF uses the standard ``log(1 + (N - df + 0.5) / (df + 0.5))`` form,
    which is non-negative for all document frequencies.
    """

    def __init__(self, k1: float = DEFAULT_K1, b: float = DEFAULT_B) -> None:
        self.k1 = k1
        self.b = b
        self._ids: list[str] = []
        self._lengths: list[int] = []
        # token -> [(document index, term frequency), ...]
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._avg_length = 0.0

    def __len__(self) -> int:
        return len(self._ids)

    def build(self, documents: list[tuple[str, list[str]]]) -> None:
        """(Re)build the index from ``(doc_id, tokens)`` pairs."""
        self._ids = [doc_id for doc_id, _ in documents]
        self._lengths = [len(tokens) for _, tokens in documents]
        self._postings = {}
        for index, (_, tokens) in enumerate(documents):
            for token, frequency in Counter(tokens).items():
                self._postings.setdefault(token, []).append((index, frequency))
        self._avg_length = (sum(self._lengths) / len(documents)) if documents else 0.0

    def search(
        self,
        query_tokens: list[str],
        *,
        top_k: int,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return up to ``top_k`` ``(doc_id, score)`` pairs, best first.

        Ties break deterministically by insertion order. ``allowed_ids``
        restricts results without affecting corpus statistics.
        """
        if not self._ids or not query_tokens or top_k <= 0:
            return []

        corpus_size = len(self._ids)
        scores: dict[int, float] = {}
        for token in dict.fromkeys(query_tokens):  # unique, order-preserving
            postings = self._postings.get(token)
            if not postings:
                continue
            document_frequency = len(postings)
            idf = log(1.0 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5))
            for index, term_frequency in postings:
                if self._avg_length > 0.0:
                    length_norm = 1.0 - self.b + self.b * (self._lengths[index] / self._avg_length)
                else:
                    length_norm = 1.0
                contribution = (
                    idf
                    * (term_frequency * (self.k1 + 1.0))
                    / (term_frequency + self.k1 * length_norm)
                )
                scores[index] = scores.get(index, 0.0) + contribution

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        results: list[tuple[str, float]] = []
        for index, score in ranked:
            doc_id = self._ids[index]
            if allowed_ids is not None and doc_id not in allowed_ids:
                continue
            results.append((doc_id, score))
            if len(results) >= top_k:
                break
        return results
