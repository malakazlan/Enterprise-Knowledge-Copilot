"""Structure-aware, page-aware text chunking.

Chunks never cross page boundaries, so every chunk maps to exactly one page —
which is what makes precise page-level citations possible downstream.

Structure awareness, in order of preference:
1. Whole paragraphs are packed into chunks; a paragraph is only cut when it
   alone exceeds the chunk budget (then the windowed splitter takes over).
2. Headings (markdown ``#``, numbered ``4.2 Title``, or ALL-CAPS lines) are
   tracked while walking the text, and every chunk after the first in a
   section is prefixed with its breadcrumb (``Section: Safety > Helmets``).
   The prefix travels with the chunk into the embedder and BM25 index, so a
   chunk that says "they must be inspected daily" still retrieves for
   "helmet inspection" — context the bare paragraph lost.
"""

from __future__ import annotations

import re

from app.services.ingestion.ports import ChunkData, ParsedDocument

# Separators tried in order when looking for a natural break near the size limit.
_SEPARATORS = ("\n\n", "\n", ". ", "? ", "! ", "; ", " ")

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(\S.*)$")
_NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*[.)]?\s+\S.*$")
_MAX_HEADING_CHARS = 80


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token)."""
    return max(1, len(text) // 4)


def _heading_level(line: str) -> tuple[int, str] | None:
    """Return (level, title) when the line reads as a heading, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    markdown = _MARKDOWN_HEADING.match(stripped)
    if markdown:
        return len(markdown.group(1)), markdown.group(2).strip()
    # Sentence-like lines (trailing punctuation) are list items, not headings.
    if stripped[-1] in ".,;:!?":
        return None
    if _NUMBERED_HEADING.match(stripped):
        return 2, stripped
    letters = [ch for ch in stripped if ch.isalpha()]
    if len(letters) >= 4 and stripped.upper() == stripped:
        return 1, stripped
    return None


class _SectionTracker:
    """Maintains the active heading breadcrumb while text is walked."""

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    def observe(self, paragraph: str) -> None:
        heading = _heading_level(paragraph.splitlines()[0]) if paragraph else None
        if heading is None:
            return
        level, title = heading
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, title))

    @property
    def breadcrumb(self) -> str | None:
        if not self._stack:
            return None
        return " > ".join(title for _, title in self._stack)


class Chunker:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        # Overlap must stay strictly below size or the window cannot advance.
        self.chunk_size = chunk_size
        self.chunk_overlap = max(0, min(chunk_overlap, chunk_size // 2))

    def chunk_document(self, parsed: ParsedDocument) -> list[ChunkData]:
        chunks: list[ChunkData] = []
        index = 0
        for page in parsed.pages:
            for piece in self._split_page(page.text):
                chunks.append(
                    ChunkData(
                        index=index,
                        content=piece,
                        page_number=page.page_number,
                        token_count=estimate_tokens(piece),
                    )
                )
                index += 1
        return chunks

    # --- structure-aware packing ---

    def _split_page(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

        tracker = _SectionTracker()
        pieces: list[str] = []
        pending: list[str] = []
        pending_len = 0
        # Breadcrumb captured when the current pending chunk started; a chunk
        # is prefixed with the section it CONTINUES, not one it introduces.
        pending_context: str | None = None
        section_chunks = 0

        def flush() -> None:
            nonlocal pending, pending_len, section_chunks
            if not pending:
                return
            content = "\n\n".join(pending)
            if pending_context and section_chunks > 0:
                content = f"Section: {pending_context}\n\n{content}"
            pieces.append(content)
            section_chunks += 1
            pending = []
            pending_len = 0

        for paragraph in paragraphs:
            started_section = _heading_level(paragraph.splitlines()[0]) is not None
            if started_section:
                flush()
                section_chunks = 0
            tracker.observe(paragraph)

            if not pending:
                pending_context = tracker.breadcrumb

            budget = self.chunk_size - (len(pending_context) + 12 if pending_context else 0)
            if len(paragraph) > budget:
                flush()
                for window in self._split_windowed(paragraph):
                    prefix = (
                        f"Section: {pending_context}\n\n"
                        if pending_context and section_chunks > 0
                        else ""
                    )
                    pieces.append(prefix + window)
                    section_chunks += 1
                pending_context = tracker.breadcrumb
                continue

            if pending_len + len(paragraph) + 2 > budget:
                flush()
                pending_context = tracker.breadcrumb
            pending.append(paragraph)
            pending_len += len(paragraph) + 2

        flush()
        return pieces

    # --- windowed fallback for oversized paragraphs ---

    def _split_windowed(self, text: str) -> list[str]:
        pieces: list[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(start + self.chunk_size, length)
            if end < length:
                end = self._find_boundary(text, start, end)
            piece = text[start:end].strip()
            if piece:
                pieces.append(piece)
            if end >= length:
                break
            start = max(end - self.chunk_overlap, start + 1)
        return pieces

    def _find_boundary(self, text: str, start: int, end: int) -> int:
        """Prefer a natural break in the second half of the window."""
        window = text[start:end]
        min_break = self.chunk_size // 2
        for separator in _SEPARATORS:
            position = window.rfind(separator)
            if position >= min_break:
                return start + position + len(separator)
        return end
