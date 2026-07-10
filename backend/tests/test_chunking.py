"""Unit tests for the page-aware chunker."""

from __future__ import annotations

from app.services.ingestion.chunking import Chunker, estimate_tokens
from app.services.ingestion.ports import ParsedDocument, ParsedPage


def _doc(*texts: str) -> ParsedDocument:
    return ParsedDocument(
        pages=[ParsedPage(page_number=i, text=text) for i, text in enumerate(texts, start=1)]
    )


def test_estimate_tokens_is_positive() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcdefgh") == 2


def test_empty_pages_yield_no_chunks() -> None:
    assert Chunker(100, 10).chunk_document(_doc("", "   ")) == []


def test_short_text_is_a_single_chunk() -> None:
    chunks = Chunker(100, 10).chunk_document(_doc("Always wear a helmet."))
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content == "Always wear a helmet."
    assert chunks[0].page_number == 1
    assert chunks[0].token_count > 0


def test_long_text_splits_with_sequential_indices() -> None:
    text = " ".join(f"word{i}" for i in range(300))
    chunks = Chunker(80, 15).chunk_document(_doc(text))
    assert len(chunks) > 1
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.content) <= 80 for chunk in chunks)
    assert all(chunk.page_number == 1 for chunk in chunks)


def test_chunks_never_cross_page_boundaries() -> None:
    chunks = Chunker(200, 20).chunk_document(_doc("Page one content.", "Page two content."))
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    for chunk in chunks:
        expected = "one" if chunk.page_number == 1 else "two"
        assert expected in chunk.content


def test_consecutive_chunks_overlap() -> None:
    # No whitespace forces fixed-width windows so overlap is exact.
    chunks = Chunker(10, 4).chunk_document(_doc("abcdefghijklmnopqrstuvwxyz0123"))
    assert len(chunks) >= 2
    assert chunks[0].content[-4:] == chunks[1].content[:4]


def test_overlap_is_clamped_below_size() -> None:
    # Overlap larger than size must not stall the window.
    chunks = Chunker(10, 999).chunk_document(_doc("abcdefghijklmnopqrstuvwxyz"))
    assert len(chunks) >= 2
