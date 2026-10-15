"""One consistent error shape for every failure:

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

Validation errors list field names and messages but never the submitted values, so a rejected
password is not echoed back or logged.
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, RateLimitedError

logger = structlog.get_logger()

_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if extra:
        body.update(extra)
    # Unhandled-exception responses are produced outside the request-context middleware, so the
    # id header is set here too. The middleware overwrites it with the same value otherwise.
    response_headers = {**(headers or {}), "X-Request-Id": request_id}
    return JSONResponse({"error": body}, status_code=status_code, headers=response_headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = None
        if isinstance(exc, RateLimitedError):
            headers = {"Retry-After": str(exc.retry_after)}
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="validation_error",
            message="The request is invalid.",
            extra={"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=_HTTP_ERROR_CODES.get(exc.status_code, "http_error"),
            message=str(exc.detail),
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Full details go to the log (with the request id); the client gets nothing internal.
        logger.exception("unhandled_error", exc_type=type(exc).__name__)
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="Something went wrong.",
        )
