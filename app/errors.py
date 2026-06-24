"""The single API error envelope and its exception handlers (CLAUDE.md §5).

Every error response — validation, HTTP, or an unhandled exception — is returned
as ``{"code", "message", "details"}``. Stack traces are logged server-side but
never leaked to a client or external recipient.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """A domain error that maps directly onto the API error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def error_envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Build the canonical error body."""
    return {"code": code, "message": message, "details": details}


def _redact_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Drop the echoed ``input`` value from each error (it may carry a secret/PII).

    The client still gets the field location, type, and message — enough to fix
    the request — without us reflecting submitted credentials back (CLAUDE.md §5).
    """
    return [{k: v for k, v in err.items() if k != "input"} for err in errors]


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every error path onto the envelope."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_envelope(
                "validation_error",
                "Request validation failed",
                _redact_validation_errors(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(f"http_{exc.status_code}", str(exc.detail), None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
        # Log the traceback server-side for diagnosis; never surface internals to
        # the client. Convention (CLAUDE.md §5): exception *messages* must not embed
        # secrets / customer PII / print contents, since they land in these logs.
        logger.exception("unhandled_exception", extra={"exc_type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope("internal_error", "Internal server error", None),
        )
