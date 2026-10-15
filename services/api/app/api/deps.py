"""FastAPI dependencies: settings, database session, authentication, CSRF, workspace access.

Order matters for tenant safety: ``get_workspace_access`` verifies membership first and only then
binds the workspace into the database transaction.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.db import bind_user, bind_workspace
from app.core.errors import ForbiddenError, NotFoundError, UnauthenticatedError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.tokens import InvalidTokenError, csrf_is_valid, decode_session_token
from app.models.user import User
from app.models.workspace import Role
from app.services import workspaces as workspace_service

SESSION_COOKIE = "sp_session"
CSRF_COOKIE = "sp_csrf"
CSRF_HEADER = "X-CSRF-Token"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class AuthRateLimiters:
    login: InMemoryRateLimiter  # keyed by client IP and email
    ip: InMemoryRateLimiter  # keyed by client IP across login and signup


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str


@dataclass(frozen=True)
class WorkspaceAccess:
    user: CurrentUser
    workspace_id: uuid.UUID
    role: Role


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_limiters(request: Request) -> AuthRateLimiters:
    limiters: AuthRateLimiters = request.app.state.limiters
    return limiters


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session  # leaving the block rolls back anything the route did not commit


SettingsDep = Annotated[Settings, Depends(get_settings_from_app)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitersDep = Annotated[AuthRateLimiters, Depends(get_limiters)]


async def verify_csrf(request: Request, settings: SettingsDep) -> None:
    """Reject state-changing requests that lack a CSRF header matching the session."""
    if request.method in _SAFE_METHODS:
        return
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token is None:
        raise UnauthenticatedError()
    supplied = request.headers.get(CSRF_HEADER)
    secret = settings.session_secret.get_secret_value()
    if not csrf_is_valid(session_token, supplied, secret=secret):
        raise ForbiddenError("CSRF token missing or invalid.", code="csrf_failed")


async def get_current_user(
    request: Request, session: SessionDep, settings: SettingsDep
) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise UnauthenticatedError()
    try:
        user_id = decode_session_token(token, secret=settings.session_secret.get_secret_value())
    except InvalidTokenError:
        raise UnauthenticatedError() from None

    await bind_user(session, user_id)
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError()
    return CurrentUser(id=user.id, email=user.email)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_workspace_access(
    workspace_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> WorkspaceAccess:
    """Resolve the caller's role in a workspace, or 404 so other tenants' ids stay hidden."""
    role = await workspace_service.get_membership_role(
        session, user_id=user.id, workspace_id=workspace_id
    )
    if role is None:
        raise NotFoundError("Workspace not found.")
    # Only now, with membership proven, is the workspace bound for row-level security.
    await bind_workspace(session, workspace_id)
    return WorkspaceAccess(user=user, workspace_id=workspace_id, role=role)


WorkspaceAccessDep = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


async def require_owner(access: WorkspaceAccessDep) -> WorkspaceAccess:
    if access.role is not Role.OWNER:
        raise ForbiddenError("Only a workspace owner can do this.")
    return access


OwnerAccessDep = Annotated[WorkspaceAccess, Depends(require_owner)]
