"""Grounded answer service: retrieve -> generate -> verify -> decide -> log.

The trust policy comes entirely from the active profile:

- ``citations_required`` and no valid citation  -> refuse
- confidence below ``confidence_threshold_refuse`` -> refuse
- confidence below ``confidence_threshold_review`` -> answer, flag for review

Every query — answered or refused — is persisted to the audit log.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.querylog import QueryLog, ReviewStatus
from app.services.generation.confidence import compute_confidence
from app.services.generation.factory import get_answer_generator
from app.services.generation.groundedness import check_groundedness
from app.services.generation.ports import AnswerGenerator, DraftAnswer, DraftCitation
from app.services.profiles.schema import RagProfile
from app.services.retrieval.service import RetrievalService
from app.services.retrieval.types import RetrievedChunk

logger = structlog.get_logger("app.generation")

REASON_NO_DOCUMENTS = "no_relevant_documents"
REASON_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
REASON_MISSING_CITATIONS = "missing_citations"
REASON_LOW_CONFIDENCE = "low_confidence"


@dataclass(slots=True)
class AnswerOutcome:
    query_id: uuid.UUID
    answer: str | None
    answered: bool
    refusal_reason: str | None
    citations: list[DraftCitation]
    confidence: float
    confidence_breakdown: dict[str, float]
    grounded_ratio: float
    needs_review: bool
    model: str
    sources_considered: int
    took_ms: float = 0.0
    retrieval_took_ms: float = 0.0


class GenerationService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        generator: AnswerGenerator | None = None,
        retrieval: RetrievalService | None = None,
    ) -> None:
        self.db = db
        self.generator = generator or get_answer_generator()
        self.retrieval = retrieval or RetrievalService(db)

    async def answer(
        self,
        query: str,
        profile: RagProfile,
        *,
        user_id: uuid.UUID | None = None,
        api_key_id: uuid.UUID | None = None,
        thread_id: uuid.UUID | None = None,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int | None = None,
        search_query: str | None = None,
    ) -> AnswerOutcome:
        started = time.perf_counter()

        # A condensed (standalone) form may drive retrieval and generation;
        # the user's original words are what gets persisted and audited.
        effective = search_query or query
        search = await self.retrieval.search(
            effective, profile, top_k=top_k, document_ids=document_ids
        )
        chunks = search.results

        if not chunks:
            outcome = self._refusal(REASON_NO_DOCUMENTS, model=self.generator.name, sources=0)
        else:
            draft = await self.generator.generate(effective, chunks, profile)
            if draft.text is None:
                outcome = self._refusal(
                    REASON_INSUFFICIENT_EVIDENCE, model=draft.model, sources=len(chunks)
                )
                # Weak-but-present retrieval still informs the audit record.
                outcome.confidence_breakdown["retrieval"] = self._retrieval_component(
                    chunks, profile
                )
            else:
                outcome = self._evaluate(draft.text, draft, chunks, profile)

        outcome.retrieval_took_ms = search.took_ms
        outcome.took_ms = round((time.perf_counter() - started) * 1000, 2)
        outcome.query_id = await self._persist(
            query, profile, outcome, user_id, api_key_id, thread_id
        )

        logger.info(
            "query_completed",
            profile=profile.name,
            answered=outcome.answered,
            refusal_reason=outcome.refusal_reason,
            confidence=outcome.confidence,
            needs_review=outcome.needs_review,
            model=outcome.model,
            took_ms=outcome.took_ms,
        )
        return outcome

    # --- internals ---

    def _refusal(self, reason: str, *, model: str, sources: int) -> AnswerOutcome:
        return AnswerOutcome(
            query_id=uuid.uuid4(),  # replaced at persist time
            answer=None,
            answered=False,
            refusal_reason=reason,
            citations=[],
            confidence=0.0,
            confidence_breakdown={"retrieval": 0.0, "groundedness": 0.0, "citations": 0.0},
            grounded_ratio=0.0,
            needs_review=False,
            model=model,
            sources_considered=sources,
        )

    def _retrieval_component(self, chunks: list[RetrievedChunk], profile: RagProfile) -> float:
        top_fused = max(chunk.fused_score for chunk in chunks)
        max_fused = 2.0 / (profile.retrieval.rrf_k + 1)
        return round(min(top_fused / max_fused, 1.0), 4) if max_fused > 0 else 0.0

    def _evaluate(
        self,
        text: str,
        draft: DraftAnswer,
        chunks: list[RetrievedChunk],
        profile: RagProfile,
    ) -> AnswerOutcome:
        generation = profile.generation

        if generation.citations_required and not draft.citations:
            outcome = self._refusal(
                REASON_MISSING_CITATIONS, model=draft.model, sources=len(chunks)
            )
            outcome.confidence_breakdown["retrieval"] = self._retrieval_component(chunks, profile)
            return outcome

        if generation.groundedness_check:
            report = check_groundedness(text, draft.marker_map())
            grounded_ratio = report.ratio if report.total_sentences > 0 else 1.0
        else:
            grounded_ratio = 1.0

        confidence, breakdown = compute_confidence(
            top_fused_score=max(chunk.fused_score for chunk in chunks),
            rrf_k=profile.retrieval.rrf_k,
            grounded_ratio=grounded_ratio,
            total_markers=draft.total_markers,
            invalid_markers=draft.invalid_markers,
            citations_required=generation.citations_required,
        )

        if confidence < generation.confidence_threshold_refuse:
            outcome = self._refusal(REASON_LOW_CONFIDENCE, model=draft.model, sources=len(chunks))
            outcome.confidence = confidence
            outcome.confidence_breakdown = breakdown
            outcome.grounded_ratio = round(grounded_ratio, 4)
            return outcome

        return AnswerOutcome(
            query_id=uuid.uuid4(),  # replaced at persist time
            answer=text,
            answered=True,
            refusal_reason=None,
            citations=draft.citations,
            confidence=confidence,
            confidence_breakdown=breakdown,
            grounded_ratio=round(grounded_ratio, 4),
            needs_review=confidence < generation.confidence_threshold_review,
            model=draft.model,
            sources_considered=len(chunks),
        )

    async def _persist(
        self,
        query: str,
        profile: RagProfile,
        outcome: AnswerOutcome,
        user_id: uuid.UUID | None,
        api_key_id: uuid.UUID | None,
        thread_id: uuid.UUID | None,
    ) -> uuid.UUID:
        log = QueryLog(
            id=uuid.uuid4(),
            user_id=user_id,
            api_key_id=api_key_id,
            thread_id=thread_id,
            profile=profile.name,
            query=query,
            answer=outcome.answer,
            answered=outcome.answered,
            refusal_reason=outcome.refusal_reason,
            confidence=outcome.confidence,
            grounded_ratio=outcome.grounded_ratio,
            needs_review=outcome.needs_review,
            review_status=ReviewStatus.PENDING if outcome.needs_review else None,
            model=outcome.model,
            citations=[
                {
                    "marker": citation.marker,
                    "chunk_id": citation.chunk.chunk_id,
                    "document_id": citation.chunk.document_id,
                    "filename": citation.chunk.filename,
                    "page_number": citation.chunk.page_number,
                }
                for citation in outcome.citations
            ],
            took_ms=outcome.took_ms,
        )
        self.db.add(log)
        await self.db.commit()
        return log.id
