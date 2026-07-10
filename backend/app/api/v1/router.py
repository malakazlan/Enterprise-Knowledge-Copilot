"""Aggregate router for API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(users.router, prefix="/users")
