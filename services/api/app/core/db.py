"""Database engine, sessions, and the per-request row-level-security context.

The API connects as the restricted ``supportpilot_app`` role. PostgreSQL policies decide which rows
that role can see, based on two transaction-local settings:

* ``app.user_id``       set once the session cookie has been verified;
* ``app.workspace_id``  set only after membership of that workspace has been verified.

``set_config(..., true)`` is local to the current transaction, so after a commit the context is gone
and queries return nothing. That is the safe default; commit once, at the end of the request.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_USER_SETTING = "app.user_id"
_WORKSPACE_SETTING = "app.workspace_id"

_SET_LOCAL = text("SELECT set_config(:name, :value, true)")


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        connect_args={
            "server_settings": {
                "application_name": "supportpilot-api",
                # Bound runaway queries and abandoned transactions (milliseconds).
                "statement_timeout": "15000",
                "idle_in_transaction_session_timeout": "30000",
            }
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set_local(session: AsyncSession, name: str, value: uuid.UUID) -> None:
    await session.execute(_SET_LOCAL, {"name": name, "value": str(value)})


async def bind_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Scope the current transaction to an authenticated user."""
    await _set_local(session, _USER_SETTING, user_id)


async def bind_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Scope the current transaction to a workspace. Call only after verifying membership."""
    await _set_local(session, _WORKSPACE_SETTING, workspace_id)
