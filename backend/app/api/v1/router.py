"""Aggregate router for API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    api_keys,
    auth,
    documents,
    evals,
    health,
    profiles,
    query,
    search,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(users.router, prefix="/users")
api_router.include_router(api_keys.router, prefix="/api-keys")
api_router.include_router(documents.router, prefix="/documents")
api_router.include_router(profiles.router, prefix="/profiles")
api_router.include_router(search.router, prefix="/search")
api_router.include_router(query.router, prefix="/query")
api_router.include_router(evals.router, prefix="/evals")
