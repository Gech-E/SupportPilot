"""Application factory: wiring only. Behaviour lives in routers, services, and core."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.deps import AuthRateLimiters
from app.api.error_handlers import register_error_handlers
from app.api.routers import auth, health, users, workspaces
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import InMemoryRateLimiter

API_PREFIX = "/api/v1"


def _build_limiters(settings: Settings) -> AuthRateLimiters:
    return AuthRateLimiters(
        login=InMemoryRateLimiter(
            max_attempts=settings.login_max_attempts,
            window_seconds=settings.auth_window_seconds,
        ),
        ip=InMemoryRateLimiter(
            max_attempts=settings.auth_ip_max_attempts,
            window_seconds=settings.auth_window_seconds,
        ),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url.get_secret_value())
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    # Interactive docs are a development convenience; they are not exposed when hardened.
    docs_enabled = not settings.is_hardened
    app = FastAPI(
        title="SupportPilot API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings
    app.state.limiters = _build_limiters(settings)

    # Added first, so it sits inside the request-context middleware and preflights still get
    # request ids and security headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-Id"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_hardened)

    register_error_handlers(app)
    app.include_router(health.router)
    for router in (auth.router, users.router, workspaces.router):
        app.include_router(router, prefix=API_PREFIX)
    return app
