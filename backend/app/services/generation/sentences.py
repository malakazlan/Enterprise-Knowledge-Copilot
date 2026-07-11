"""Sentence splitting and content-token extraction for generation."""

from __future__ import annotations

import re

from app.services.retrieval.tokenize import tokenize

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKER_RE = re.compile(r"\[(\d+)\]")
_LEADING_MARKERS_RE = re.compile(r"^(?:\s*\[\d+\])+")

# Minimal English stopword set — enough to keep function words from inflating
# lexical-overlap scores without dragging in an NLP dependency.
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "with",
        "as",
        "at",
        "by",
        "from",
        "into",
        "will",
        "shall",
        "can",
        "may",
        "not",
        "no",
        "do",
        "does",
        "did",
        "has",
        "have",
        "had",
        "they",
        "them",
        "their",
        "there",
        "which",
        "who",
        "whom",
    }
)


def split_sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation and newlines.

    Citation markers that end up at the *start* of a fragment belong to the
    preceding sentence — LLMs habitually write "Claim. [1] Next claim." — so
    leading markers are reattached to keep groundedness attribution correct.
    """
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text.strip()) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if merged:
            match = _LEADING_MARKERS_RE.match(part)
            if match:
                merged[-1] = f"{merged[-1]} {match.group(0).strip()}"
                remainder = part[match.end() :].strip()
                if remainder.strip(" .,;:!?"):  # skip fragments that are only punctuation
                    merged.append(remainder)
                continue
        merged.append(part)
    return merged


def sentence_markers(sentence: str) -> list[int]:
    """Citation markers referenced in a sentence, in order of appearance."""
    return [int(match) for match in _MARKER_RE.findall(sentence)]


def content_tokens(text: str) -> set[str]:
    """Tokens that carry meaning for lexical-overlap comparisons."""
    return {token for token in tokenize(text) if len(token) > 2 and token not in _STOPWORDS}


def strip_markers(text: str) -> str:
    return _MARKER_RE.sub("", text)
