"""HTTP surface checks that need no database: headers, request ids, CORS, docs exposure."""

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app

ALLOWED_ORIGIN = "https://app.example.com"


def make_app(**overrides: Any) -> FastAPI:
    values: dict[str, Any] = {
        "_env_file": None,
        "database_url": SecretStr("postgresql+asyncpg://u:p@localhost:1/none"),
        "session_secret": SecretStr("s" * 48),
        "app_env": "test",
        "cors_origins": [ALLOWED_ORIGIN],
    }
    values.update(overrides)
    return create_app(Settings(**values))


def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def test_liveness_needs_no_database() -> None:
    async with client_for(make_app()) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_security_headers_are_present() -> None:
    async with client_for(make_app()) as client:
        response = await client.get("/health")
    headers = response.headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "strict-transport-security" not in headers  # only when hardened


async def test_hsts_is_sent_when_hardened_and_docs_are_disabled() -> None:
    app = make_app(app_env="production")
    async with client_for(app) as client:
        health = await client.get("/health")
        docs = await client.get("/docs")
        schema = await client.get("/openapi.json")
    assert "max-age=" in health.headers["strict-transport-security"]
    assert docs.status_code == 404
    assert schema.status_code == 404


async def test_docs_are_available_outside_production() -> None:
    async with client_for(make_app(app_env="local")) as client:
        response = await client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


async def test_well_formed_request_id_is_echoed() -> None:
    async with client_for(make_app()) as client:
        response = await client.get("/health", headers={"X-Request-Id": "abc12345-trace_01"})
    assert response.headers["x-request-id"] == "abc12345-trace_01"


async def test_malformed_request_id_is_replaced() -> None:
    async with client_for(make_app()) as client:
        response = await client.get("/health", headers={"X-Request-Id": "bad id with spaces!"})
    assert response.headers["x-request-id"] != "bad id with spaces!"
    assert len(response.headers["x-request-id"]) == 32


async def test_unknown_route_uses_the_standard_error_shape() -> None:
    async with client_for(make_app()) as client:
        response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["x-request-id"]


async def test_cors_allows_the_configured_origin_with_credentials() -> None:
    async with client_for(make_app()) as client:
        response = await client.options(
            "/api/v1/me",
            headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "GET"},
        )
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_cors_refuses_other_origins() -> None:
    async with client_for(make_app()) as client:
        response = await client.options(
            "/api/v1/me",
            headers={"Origin": "https://evil.example.net", "Access-Control-Request-Method": "GET"},
        )
    assert "access-control-allow-origin" not in response.headers
