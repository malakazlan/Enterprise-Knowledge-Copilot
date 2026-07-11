"""Grounded-answer prompt construction for LLM-backed generation."""

from __future__ import annotations

from app.services.generation.ports import INSUFFICIENT_EVIDENCE
from app.services.profiles.schema import RagProfile
from app.services.retrieval.types import RetrievedChunk

_DEFAULT_SYSTEM_PROMPT = f"""\
You are a document-grounded assistant for an enterprise knowledge base.

Rules — follow every one of them:
1. Answer using ONLY the numbered sources provided. Never use outside knowledge.
2. Cite evidence: end every factual sentence with the marker(s) of the \
source(s) that support it, e.g. "Workers must wear helmets [1]." Place the \
marker before the final punctuation.
3. If the sources do not contain the information needed to answer, reply with \
exactly: {INSUFFICIENT_EVIDENCE}
4. Never fabricate citations. Only use markers that appear in the sources.
5. Be concise and factual. Quote figures, section numbers, and terms exactly \
as written in the sources."""


def build_system_prompt(profile: RagProfile) -> str:
    """Profile system-prompt override wins; the grounding rules are appended
    regardless so no profile can accidentally disable citation discipline."""
    if profile.generation.system_prompt:
        return f"{profile.generation.system_prompt.strip()}\n\n{_DEFAULT_SYSTEM_PROMPT}"
    return _DEFAULT_SYSTEM_PROMPT


def build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for position, chunk in enumerate(chunks, start=1):
        origin = chunk.title or chunk.filename
        page = f", page {chunk.page_number}" if chunk.page_number is not None else ""
        blocks.append(f"[{position}] ({origin}{page})\n{chunk.content}")
    sources = "\n\n".join(blocks)
    return f"Sources:\n\n{sources}\n\nQuestion: {query}"
