"""Evaluation harness API — admin only.

Golden datasets measure the live pipeline. Runs execute synchronously (golden
sets are deliberately small); large-scale async runs move to Celery later.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, Principal, require_principal_roles
from app.core.exceptions import NotFoundError
from app.models.evals import EvalCase, EvalDataset
from app.models.user import UserRole
from app.schemas.evals import (
    EvalCaseCreate,
    EvalCaseRead,
    EvalDatasetCreate,
    EvalDatasetDetail,
    EvalDatasetRead,
    EvalRunRead,
    EvalRunRequest,
)
from app.services.evals.service import EvalService
from app.services.profiles.loader import DEFAULT_PROFILE, get_profile

router = APIRouter(
    tags=["evals"], dependencies=[Depends(require_principal_roles(UserRole.ADMIN))]
)

AdminPrincipal = Annotated[Principal, Depends(require_principal_roles(UserRole.ADMIN))]


async def _dataset_or_404(service: EvalService, dataset_id: uuid.UUID) -> EvalDataset:
    dataset = await service.get_dataset(dataset_id)
    if dataset is None:
        raise NotFoundError("Eval dataset not found.")
    return dataset


@router.post(
    "/datasets",
    response_model=EvalDatasetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an eval dataset",
)
async def create_dataset(
    payload: EvalDatasetCreate, db: DbSession, principal: AdminPrincipal
) -> EvalDatasetRead:
    if payload.profile is not None:
        get_profile(payload.profile)  # 404 on unknown profile
    dataset = EvalDataset(
        id=uuid.uuid4(),
        name=payload.name,
        description=payload.description,
        profile=payload.profile,
        created_by=principal.user_id,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return EvalDatasetRead.model_validate(dataset)


@router.get("/datasets", response_model=list[EvalDatasetRead], summary="List eval datasets")
async def list_datasets(db: DbSession) -> list[EvalDatasetRead]:
    datasets = await EvalService(db).list_datasets()
    return [EvalDatasetRead.model_validate(dataset) for dataset in datasets]


@router.get(
    "/datasets/{dataset_id}",
    response_model=EvalDatasetDetail,
    summary="Get a dataset with its cases",
)
async def get_dataset(db: DbSession, dataset_id: uuid.UUID) -> EvalDatasetDetail:
    service = EvalService(db)
    dataset = await _dataset_or_404(service, dataset_id)
    cases = await service.list_cases(dataset.id)
    detail = EvalDatasetDetail.model_validate(
        {**EvalDatasetRead.model_validate(dataset).model_dump(), "cases": cases}
    )
    return detail


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset with its cases and runs",
)
async def delete_dataset(db: DbSession, dataset_id: uuid.UUID) -> None:
    service = EvalService(db)
    dataset = await _dataset_or_404(service, dataset_id)
    await service.delete_dataset(dataset)


@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=EvalCaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a case to a dataset",
)
async def add_case(payload: EvalCaseCreate, db: DbSession, dataset_id: uuid.UUID) -> EvalCaseRead:
    service = EvalService(db)
    dataset = await _dataset_or_404(service, dataset_id)
    case = EvalCase(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        question=payload.question,
        expected_document_id=payload.expected_document_id,
        expected_page=payload.expected_page,
        expected_keywords=payload.expected_keywords,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return EvalCaseRead.model_validate(case)


@router.post(
    "/datasets/{dataset_id}/run",
    response_model=EvalRunRead,
    summary="Run the dataset against the live pipeline",
)
async def run_dataset(
    payload: EvalRunRequest, db: DbSession, principal: AdminPrincipal, dataset_id: uuid.UUID
) -> EvalRunRead:
    service = EvalService(db)
    dataset = await _dataset_or_404(service, dataset_id)
    profile = get_profile(payload.profile or dataset.profile or DEFAULT_PROFILE)
    run = await service.run_dataset(dataset, profile, created_by=principal.user_id)
    return EvalRunRead.model_validate(run)


@router.get(
    "/datasets/{dataset_id}/runs",
    response_model=list[EvalRunRead],
    summary="List runs for a dataset (newest first)",
)
async def list_runs(db: DbSession, dataset_id: uuid.UUID) -> list[EvalRunRead]:
    service = EvalService(db)
    dataset = await _dataset_or_404(service, dataset_id)
    runs = await service.list_runs(dataset.id)
    return [EvalRunRead.model_validate(run) for run in runs]
