"""Request context middleware (pure ASGI, so streaming responses keep working later).

For every HTTP request it:
* assigns a request id (accepting a well-formed client one, otherwise generating one),
* adds security headers to the response,
* logs one structured line when the request completes (method, path, status, duration only).
"""

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger()

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/openapi.json"})

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
    # API responses carry personal data: never let a shared cache store them.
    "Cache-Control": "no-store",
}
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_HSTS = "max-age=63072000; includeSubDomains"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._resolve_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_code = 500
        extra_headers = self._response_headers(scope["path"])

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = request_id
                for name, value in extra_headers.items():
                    headers.setdefault(name, value)
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            logger.info(
                "request_completed",
                method=scope["method"],
                path=scope["path"],
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )

    @staticmethod
    def _resolve_request_id(scope: Scope) -> str:
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                candidate = value.decode("latin-1")
                if _REQUEST_ID_PATTERN.fullmatch(candidate):
                    return candidate
                break
        return uuid.uuid4().hex

    def _response_headers(self, path: str) -> dict[str, str]:
        headers = dict(_SECURITY_HEADERS)
        if path not in _DOCS_PATHS:
            # The interactive docs (local development only) need scripts and styles to load.
            headers["Content-Security-Policy"] = _API_CSP
        if self._hsts:
            headers["Strict-Transport-Security"] = _HSTS
        return headers
