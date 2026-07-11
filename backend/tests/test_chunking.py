"""Unit tests for the page-aware chunker."""

from __future__ import annotations

from app.services.ingestion.chunking import Chunker, _heading_level, estimate_tokens
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


def _single_page(text: str) -> ParsedDocument:
    return ParsedDocument(pages=[ParsedPage(page_number=1, text=text)])


def test_paragraphs_are_never_cut_when_they_fit() -> None:
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    chunks = Chunker(chunk_size=48, chunk_overlap=8).chunk_document(_single_page(text))
    # Splits happen only at paragraph boundaries.
    for chunk in chunks:
        for piece in chunk.content.split("\n\n"):
            assert piece in text
    joined = " ".join(chunk.content for chunk in chunks)
    assert "First paragraph here." in joined and "Third paragraph here." in joined


def test_continuation_chunks_carry_section_context() -> None:
    body = "\n\n".join(f"Helmet rule number {i} applies to workers." for i in range(1, 9))
    text = f"# Safety Manual\n\n## Helmets\n\n{body}"
    chunks = Chunker(chunk_size=120, chunk_overlap=10).chunk_document(_single_page(text))
    assert len(chunks) > 2
    # The chunk that introduces a section carries no prefix; continuations do.
    intro = next(c for c in chunks if "## Helmets" in c.content)
    assert not intro.content.startswith("Section:")
    continuations = [c for c in chunks if c.index > intro.index]
    assert continuations
    for chunk in continuations:
        assert chunk.content.startswith("Section: Safety Manual > Helmets"), chunk.content


def test_numbered_and_caps_headings_are_detected() -> None:
    assert _heading_level("4.2 Protective Equipment") == (2, "4.2 Protective Equipment")
    assert _heading_level("APPENDIX B") == (1, "APPENDIX B")
    # List items and prose are not headings.
    assert _heading_level("1. First, put on the helmet.") is None
    assert _heading_level("this is an ordinary sentence") is None


def test_oversized_paragraph_falls_back_to_windowed_split() -> None:
    text = "## Terms\n\n" + ("word " * 200).strip()
    chunks = Chunker(chunk_size=100, chunk_overlap=20).chunk_document(_single_page(text))
    assert len(chunks) > 3
    for chunk in chunks:
        assert len(chunk.content) <= 100 + len("Section: Terms\n\n")
