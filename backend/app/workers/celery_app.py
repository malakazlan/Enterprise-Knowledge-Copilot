"""Celery application for asynchronous ingestion work."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "enterprise_knowledge_copilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# Discover tasks in app.workers.tasks.
celery_app.autodiscover_tasks(["app.workers"])
