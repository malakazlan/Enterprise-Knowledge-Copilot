"""Celery tasks that drive the ingestion pipeline off the request path."""

from __future__ import annotations

import asyncio
import uuid

import structlog

from app.db.session import AsyncSessionLocal
from app.services.ingestion.factory import get_storage
from app.services.ingestion.pipeline import IngestionPipeline
from app.workers.celery_app import celery_app

logger = structlog.get_logger("app.worker")


@celery_app.task(name="ingestion.run", bind=True, max_retries=3, default_retry_delay=30)
def run_ingestion(self: object, job_id: str) -> str:
    """Execute an ingestion job. Returns the terminal job status."""

    async def _run() -> str:
        async with AsyncSessionLocal() as session:
            pipeline = IngestionPipeline(session, get_storage())
            job = await pipeline.run(uuid.UUID(job_id))
            return job.status.value

    logger.info("worker_ingestion_start", job_id=job_id)
    return asyncio.run(_run())
