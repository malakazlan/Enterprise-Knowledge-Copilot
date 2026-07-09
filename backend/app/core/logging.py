"""Structured logging configuration built on ``structlog`` + stdlib ``logging``.

All application and third-party (uvicorn, sqlalchemy, ...) log records flow
through a single ``structlog`` formatter, so output is consistent — JSON in
production, coloured console locally.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings

_configured = False


def configure_logging() -> None:
    """Configure structlog and route stdlib logging through it. Idempotent."""
    global _configured
    if _configured:
        return

    level = logging.getLevelName(settings.log_level)
    if not isinstance(level, int):
        level = logging.INFO

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Processors shared between structlog-native and foreign (stdlib) records.
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Let uvicorn's records propagate to the root handler instead of duplicating.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
