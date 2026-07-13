"""Parent-child expansion: small chunks match, bigger windows generate.

Retrieval stays precise on small chunks; before generation, each hit is
widened with its immediate neighbours (chunk_index ± 1 within the same
document). Citations, snippets, and page numbers keep pointing at the exact
matched chunk — only what the generator reads gets wider.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.services.retrieval.types import RetrievedChunk


async def expand_neighbors(db: AsyncSession, chunks: list[RetrievedChunk]) -> None:
    """Populate `expanded_content` on each hit with prev + self + next text."""
    if not chunks:
        return

    hit_ids = {chunk.chunk_id for chunk in chunks}
    wanted: set[tuple[uuid.UUID, int]] = set()
    for chunk in chunks:
        document_id = uuid.UUID(chunk.document_id)
        wanted.add((document_id, chunk.chunk_index - 1))
        wanted.add((document_id, chunk.chunk_index + 1))
    if not wanted:
        return

    result = await db.execute(
        select(DocumentChunk).where(
            or_(
                *(
                    tuple_(DocumentChunk.document_id, DocumentChunk.chunk_index) == pair
                    for pair in wanted
                )
            )
        )
    )
    neighbors = {(row.document_id, row.chunk_index): row for row in result.scalars().all()}

    for chunk in chunks:
        document_id = uuid.UUID(chunk.document_id)
        parts: list[str] = []
        previous = neighbors.get((document_id, chunk.chunk_index - 1))
        # A neighbour that is itself a hit renders as its own source block —
        # repeating it here would just duplicate prompt tokens.
        if previous is not None and str(previous.id) not in hit_ids:
            parts.append(previous.content)
        parts.append(chunk.content)
        following = neighbors.get((document_id, chunk.chunk_index + 1))
        if following is not None and str(following.id) not in hit_ids:
            parts.append(following.content)
        if len(parts) > 1:
            chunk.expanded_content = "\n\n".join(parts)
