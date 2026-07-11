"""HTTP middleware: request-scoped context, access logging, and metrics."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY

logger = structlog.get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
PROCESS_TIME_HEADER = "X-Process-Time-Ms"

# The console is a self-contained single file, so the CSP can deny everything
# external; 'unsafe-inline' is the deliberate tradeoff of the no-build-chain
# design (no CDNs, no third-party scripts to compromise).
_CONSOLE_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers on every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path == "/":
            response.headers.setdefault("Content-Security-Policy", _CONSOLE_CSP)
        return response


def _route_template(request: Request) -> str:
    """Return the matched route pattern to keep metric label cardinality low."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id + structured context and record latency/metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - start
            template = _route_template(request)
            REQUEST_COUNT.labels(request.method, template, 500).inc()
            REQUEST_LATENCY.labels(request.method, template).observe(duration)
            logger.exception("request_failed", duration_ms=round(duration * 1000, 2))
            structlog.contextvars.clear_contextvars()
            raise

        duration = time.perf_counter() - start
        template = _route_template(request)
        REQUEST_COUNT.labels(request.method, template, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, template).observe(duration)

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[PROCESS_TIME_HEADER] = f"{duration * 1000:.2f}"
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        structlog.contextvars.clear_contextvars()
        return response
