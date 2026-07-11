"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import NotFoundError, register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.metrics import render_metrics
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

_STATIC_DIR = Path(__file__).parent / "static"


def _frontend_dist() -> Path:
    """Static export of the Next.js app. Absent in API-only deploys."""
    if settings.frontend_dist:
        return Path(settings.frontend_dist)
    return Path(__file__).resolve().parents[2] / "frontend" / "out"


def _run_migrations() -> None:
    """Apply Alembic migrations to head (runs in a worker thread)."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    root = Path(__file__).resolve().parent.parent  # directory holding alembic.ini
    config = AlembicConfig(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    import asyncio

    logger = get_logger("app.lifecycle")
    if settings.auto_migrate:
        logger.info("migrating_database")
        await asyncio.to_thread(_run_migrations)
    logger.info("startup", environment=settings.environment, version=__version__)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Production RAG & document intelligence API.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS is added last so it wraps everything and applies to error responses.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/console", include_in_schema=False)
    async def console() -> FileResponse:
        """Self-contained fallback console (single file, no build chain)."""
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

    # Unknown API paths must keep the JSON error envelope even when the static
    # frontend mount below would otherwise swallow them with an HTML 404.
    @app.api_route(
        "/api/{_rest:path}",
        include_in_schema=False,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def api_not_found(_rest: str) -> None:
        raise NotFoundError("Not found.")

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    frontend_dist = _frontend_dist()
    if frontend_dist.is_dir():
        # Serves /, /ask/, /_next/… — routes above win, everything else falls
        # through to the exported app.
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> FileResponse:
            """No frontend build present; serve the fallback console."""
            return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

    return app


app = create_app()
