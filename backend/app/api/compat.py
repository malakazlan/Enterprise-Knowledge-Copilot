"""OpenAI-compatible surface: /v1/chat/completions and /v1/models.

Any OpenAI-SDK client integrates with one line:

    client = OpenAI(base_url="https://kb.company.internal/v1", api_key="ekc_...")

`model` selects a domain profile (unknown names fall back to the default).
Answers come back grounded and cited, with an `ekc` extension object carrying
the trust signals (answered, confidence, needs_review, citations) — standard
clients ignore it; workflow code can branch on it. Streaming follows the
verified-answer rule: the pipeline finishes before the first token is sent.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, DbSession, limit_query_rate
from app.api.v1.endpoints.query import _answer_one
from app.core.exceptions import ValidationAppError
from app.schemas.query import QueryRequest, QueryResponse
from app.services.ingestion.chunking import estimate_tokens
from app.services.profiles.loader import list_profile_names

router = APIRouter(tags=["openai-compat"], dependencies=[Depends(limit_query_rate)])


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            return " ".join(
                str(part.get("text", "")) for part in self.content if part.get("type") == "text"
            ).strip()
        return ""


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    # Accepted-and-ignored OpenAI knobs (grounding controls generation here).
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None


def _resolve_profile(model: str) -> str | None:
    name = model.removeprefix("ekc/").removeprefix("ekc:")
    return name if name in list_profile_names() else None


def _content_from(response: QueryResponse) -> str:
    if not response.answered or not response.answer:
        reason = response.refusal_reason or "insufficient_evidence"
        return (
            "I can't answer that from the knowledge base "
            f"(reason: {reason}). No answer is safer than a wrong one."
        )
    lines = [response.answer]
    if response.citations:
        lines.append("")
        lines.append("Sources:")
        for citation in response.citations:
            page = f", p.{citation.page_number}" if citation.page_number is not None else ""
            lines.append(f"[{citation.marker}] {citation.filename}{page}")
    return "\n".join(lines)


def _ekc_extension(response: QueryResponse) -> dict[str, Any]:
    return {
        "answered": response.answered,
        "confidence": response.confidence,
        "needs_review": response.needs_review,
        "refusal_reason": response.refusal_reason,
        "citations": [
            {
                "marker": c.marker,
                "filename": c.filename,
                "page": c.page_number,
                "document_id": str(c.document_id),
            }
            for c in response.citations
        ],
    }


@router.get("/models", summary="Profiles, presented as models")
async def list_models(_principal: CurrentPrincipal) -> dict[str, Any]:
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "created": created, "owned_by": "ekc"}
            for name in list_profile_names()
        ],
    }


@router.post("/chat/completions", summary="OpenAI-compatible grounded chat")
async def chat_completions(
    payload: ChatCompletionRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    background: BackgroundTasks,
) -> Any:
    user_messages = [m for m in payload.messages if m.role == "user" and m.text()]
    if not user_messages:
        raise ValidationAppError("At least one user message with text content is required.")
    question = user_messages[-1].text()

    response = await _answer_one(
        QueryRequest(query=question, profile=_resolve_profile(payload.model)),
        db,
        principal,
        background,
    )

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    content = _content_from(response)
    base: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": response.profile,
    }

    if not payload.stream:
        return {
            **base,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": estimate_tokens(question),
                "completion_tokens": estimate_tokens(content),
                "total_tokens": estimate_tokens(question) + estimate_tokens(content),
            },
            "ekc": _ekc_extension(response),
        }

    async def chunks() -> AsyncIterator[str]:
        chunk_base = {**base, "object": "chat.completion.chunk"}
        first = {
            **chunk_base,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(first)}\n\n"
        words = content.split(" ")
        for i in range(0, len(words), 4):
            delta = {
                **chunk_base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": " ".join(words[i : i + 4]) + " "},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(delta)}\n\n"
        final = {
            **chunk_base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "ekc": _ekc_extension(response),
        }
        yield f"data: {json.dumps(final)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        chunks(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
