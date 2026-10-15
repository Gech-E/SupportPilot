"""Alembic environment.

Migrations run as the database *owner* role, read from MIGRATION_DATABASE_URL. The API itself never
uses this URL: at request time it connects as the restricted ``supportpilot_app`` role.
"""

import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config


def _database_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("MIGRATION_DATABASE_URL is not set")
    return url


def _run_migrations(connection: Connection) -> None:
    # No SQLAlchemy metadata: migrations are explicit SQL so RLS policies stay reviewable.
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_online())


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run against a database.")

run_migrations_online()
