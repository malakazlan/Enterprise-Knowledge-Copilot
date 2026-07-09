"""Application error hierarchy and FastAPI exception handlers.

Every error response shares one envelope so clients can rely on a stable shape::

    {"error": {"code": "not_found", "message": "...", "details": {...},
               "request_id": "..."}}
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base class for expected, domain-level application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"
    message = "The request conflicts with the current state."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"
    message = "Authentication is required or has failed."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "permission_denied"
    message = "You do not have permission to perform this action."


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"
    message = "The request payload failed validation."


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limited"
    message = "Too many requests. Please retry later."


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "service_unavailable"
    message = "A downstream service is unavailable."


def _envelope(
    request: Request,
    *,
    code: str,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    return {"error": body}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers producing the shared error envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("app_error", code=exc.error_code, message=exc.message)
        else:
            logger.info("app_error", code=exc.error_code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                request, code=exc.error_code, message=exc.message, details=exc.details
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope(
                request,
                code="validation_error",
                message="The request payload failed validation.",
                details=jsonable_encoder(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                request,
                code="http_error",
                message=str(exc.detail),
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                request,
                code="internal_error",
                message="An unexpected error occurred.",
            ),
        )
