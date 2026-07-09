"""Liveness and readiness probes.

``/live`` reports that the process is running. ``/ready`` reports whether the
service can serve traffic; dependency checks (database, cache, vector store)
are added here as those subsystems come online in later phases.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import settings

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ReadinessCheck(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class ReadinessStatus(BaseModel):
    status: str
    checks: list[ReadinessCheck]


@router.get("/live", response_model=HealthStatus, summary="Liveness probe")
async def liveness() -> HealthStatus:
    return HealthStatus(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessStatus, summary="Readiness probe")
async def readiness() -> ReadinessStatus:
    checks: list[ReadinessCheck] = []
    healthy = all(check.healthy for check in checks)
    return ReadinessStatus(status="ok" if healthy else "degraded", checks=checks)
