"""Integration fixtures: a real PostgreSQL database, migrated by Alembic, used as in production.

Point the tests at a server with:

    TEST_ADMIN_DSN=postgresql://postgres:<password>@localhost:5432/postgres   (a superuser)
    TEST_APP_PASSWORD=<any throwaway value>

A scratch database ``supportpilot_test`` is created, migrated, and dropped afterwards. The API under
test connects as the restricted ``supportpilot_app`` role, exactly like production, so row-level
security is really exercised.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings
from app.main import create_app

API_DIR = Path(__file__).resolve().parents[2]
SCRATCH_DB = "supportpilot_test"
APP_ROLE = "supportpilot_app"
ADMIN_DSN = os.environ.get("TEST_ADMIN_DSN", "postgresql://postgres@127.0.0.1:5432/postgres")
APP_PASSWORD = os.environ.get("TEST_APP_PASSWORD", "test_app_password")


@dataclass(frozen=True)
class DatabaseUrls:
    admin_dsn: str  # asyncpg DSN, superuser, scratch database
    app_dsn: str  # asyncpg DSN, restricted role, scratch database
    admin_sqlalchemy: str
    app_sqlalchemy: str


def _render(url: URL, driver: str) -> str:
    return url.set(drivername=driver).render_as_string(hide_password=False)


def _database_urls() -> DatabaseUrls:
    admin_url = make_url(ADMIN_DSN).set(database=SCRATCH_DB)
    app_url = admin_url.set(username=APP_ROLE, password=APP_PASSWORD)
    return DatabaseUrls(
        admin_dsn=_render(admin_url, "postgresql"),
        app_dsn=_render(app_url, "postgresql"),
        admin_sqlalchemy=_render(admin_url, "postgresql+asyncpg"),
        app_sqlalchemy=_render(app_url, "postgresql+asyncpg"),
    )


async def _provision_database() -> None:
    connection = await asyncpg.connect(ADMIN_DSN)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
        role_exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", APP_ROLE
        )
        if not role_exists:
            await connection.execute(f"CREATE ROLE {APP_ROLE} LOGIN")
        # DDL cannot take bind parameters, so let the server quote the password safely.
        alter_statement = await connection.fetchval(
            "SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOBYPASSRLS', $1::text, $2::text)",
            APP_ROLE,
            APP_PASSWORD,
        )
        await connection.execute(alter_statement)
    finally:
        await connection.close()


async def _drop_database() -> None:
    connection = await asyncpg.connect(ADMIN_DSN)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
    finally:
        await connection.close()


def _run_migrations(urls: DatabaseUrls) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env={**os.environ, "MIGRATION_DATABASE_URL": urls.admin_sqlalchemy},
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def database_urls() -> Iterator[DatabaseUrls]:
    urls = _database_urls()
    asyncio.run(_provision_database())
    _run_migrations(urls)
    yield urls
    asyncio.run(_drop_database())


@pytest.fixture(autouse=True)
async def clean_database(database_urls: DatabaseUrls) -> None:
    """Every test starts from empty tables (TRUNCATE is not subject to row-level security)."""
    connection = await asyncpg.connect(database_urls.admin_dsn)
    try:
        await connection.execute("TRUNCATE memberships, workspaces, users CASCADE")
    finally:
        await connection.close()


@pytest.fixture
async def admin_connection(database_urls: DatabaseUrls) -> AsyncIterator[asyncpg.Connection]:
    """A superuser connection for arranging data that the API itself must not be able to write."""
    connection = await asyncpg.connect(database_urls.admin_dsn)
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
def settings(database_urls: DatabaseUrls) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(database_urls.app_sqlalchemy),
        session_secret=SecretStr("integration-test-secret-" + "x" * 32),
        cookie_secure=True,
        cors_origins=["https://app.example.com"],
        login_max_attempts=3,
        auth_ip_max_attempts=100,
        auth_window_seconds=300,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    # httpx does not run ASGI lifespan events, so run them explicitly.
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client_factory(app: FastAPI) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Each client has its own cookie jar, so one test can act as several users."""
    clients: list[AsyncClient] = []

    def make() -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()


@pytest.fixture
def client(client_factory: Callable[[], AsyncClient]) -> AsyncClient:
    return client_factory()
