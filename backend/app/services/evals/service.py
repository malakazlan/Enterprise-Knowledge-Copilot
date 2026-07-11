"""Evaluation runner: score the live pipeline against a golden dataset.

Each case runs the real retrieval and generation paths — the same code serving
``/search`` and ``/query`` — so measured numbers reflect what users actually
get with the evaluated profile.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evals import EvalCase, EvalDataset, EvalRun
from app.services.evals.metrics import aggregate, keyword_recall, page_hit, reciprocal_rank
from app.services.generation.service import GenerationService
from app.services.profiles.schema import RagProfile
from app.services.retrieval.service import RetrievalService

logger = structlog.get_logger("app.evals")


class EvalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.retrieval = RetrievalService(db)
        self.generation = GenerationService(db)

    # --- dataset/case persistence ---

    async def get_dataset(self, dataset_id: uuid.UUID) -> EvalDataset | None:
        return await self.db.get(EvalDataset, dataset_id)

    async def list_datasets(self) -> Sequence[EvalDataset]:
        result = await self.db.execute(select(EvalDataset).order_by(EvalDataset.created_at))
        return result.scalars().all()

    async def list_cases(self, dataset_id: uuid.UUID) -> Sequence[EvalCase]:
        result = await self.db.execute(
            select(EvalCase).where(EvalCase.dataset_id == dataset_id).order_by(EvalCase.created_at)
        )
        return result.scalars().all()

    async def list_runs(self, dataset_id: uuid.UUID) -> Sequence[EvalRun]:
        result = await self.db.execute(
            select(EvalRun)
            .where(EvalRun.dataset_id == dataset_id)
            .order_by(desc(EvalRun.created_at))
        )
        return result.scalars().all()

    async def delete_dataset(self, dataset: EvalDataset) -> None:
        # Explicit child cleanup: portable across engines (see DocumentService).
        await self.db.execute(delete(EvalCase).where(EvalCase.dataset_id == dataset.id))
        await self.db.execute(delete(EvalRun).where(EvalRun.dataset_id == dataset.id))
        await self.db.delete(dataset)
        await self.db.commit()

    # --- execution ---

    async def run_dataset(
        self,
        dataset: EvalDataset,
        profile: RagProfile,
        *,
        created_by: uuid.UUID | None = None,
    ) -> EvalRun:
        cases = await self.list_cases(dataset.id)
        results: list[dict[str, Any]] = []

        for case in cases:
            results.append(await self._run_case(case, profile))

        run = EvalRun(
            id=uuid.uuid4(),
            dataset_id=dataset.id,
            profile=profile.name,
            case_count=len(cases),
            metrics=aggregate(results),
            results=results,
            created_by=created_by,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        logger.info(
            "eval_run_completed",
            dataset=dataset.name,
            profile=profile.name,
            cases=len(cases),
            metrics=run.metrics,
        )
        return run

    async def _run_case(self, case: EvalCase, profile: RagProfile) -> dict[str, Any]:
        expected_doc = str(case.expected_document_id) if case.expected_document_id else None

        # Retrieval judgement against the same /search path users hit.
        search = await self.retrieval.search(case.question, profile)
        ranked_docs = [chunk.document_id for chunk in search.results]
        ranked_pages = [(chunk.document_id, chunk.page_number) for chunk in search.results]

        rr: float | None = None
        page_ok: bool | None = None
        if expected_doc is not None:
            rr = reciprocal_rank(ranked_docs, expected_doc)
            if case.expected_page is not None:
                page_ok = page_hit(ranked_pages, expected_doc, case.expected_page)

        # Answer judgement against the same /query path (retrieval runs again
        # inside; acceptable for offline-sized datasets, revisit for scale).
        answer = await self.generation.answer(case.question, profile)
        cited_docs = {citation.chunk.document_id for citation in answer.citations}

        citation_ok: bool | None = None
        if expected_doc is not None:
            citation_ok = expected_doc in cited_docs

        kw_recall: float | None = None
        if case.expected_keywords:
            kw_recall = round(keyword_recall(answer.answer, case.expected_keywords), 4)

        return {
            "case_id": str(case.id),
            "question": case.question,
            "reciprocal_rank": rr,
            "page_hit": page_ok,
            "answered": answer.answered,
            "refusal_reason": answer.refusal_reason,
            "citation_hit": citation_ok,
            "keyword_recall": kw_recall,
            "confidence": answer.confidence,
            "grounded_ratio": answer.grounded_ratio,
        }
