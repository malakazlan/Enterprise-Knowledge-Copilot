"""Shared tokenizer for the sparse channel and lexical reranking.

Lowercased alphanumeric tokens. Numbers are kept deliberately — part numbers,
statute references, and error codes are high-value exact-match queries in the
target domains.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())
