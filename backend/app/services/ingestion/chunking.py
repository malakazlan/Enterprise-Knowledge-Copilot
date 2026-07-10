"""Page-aware text chunking.

Chunks never cross page boundaries, so every chunk maps to exactly one page —
which is what makes precise page-level citations possible downstream.
"""

from __future__ import annotations

from app.services.ingestion.ports import ChunkData, ParsedDocument

# Separators tried in order when looking for a natural break near the size limit.
_SEPARATORS = ("\n\n", "\n", ". ", "? ", "! ", "; ", " ")


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token)."""
    return max(1, len(text) // 4)


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
            for piece in self._split(page.text):
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

    def _split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

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
