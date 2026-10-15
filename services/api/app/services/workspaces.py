"""Workspace lifecycle and membership queries.

Row-level security is the second line of defense behind these functions: callers must already have
verified the user's membership and bound the transaction (see ``app/api/deps.py``).
"""

import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.db import bind_workspace
from app.core.errors import ForbiddenError, NotFoundError
from app.models.user import User
from app.models.workspace import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DAILY_TOKEN_BUDGET,
    Membership,
    Role,
    Workspace,
)

# Only these columns can be changed through an update; anything else is a programming error.
_UPDATABLE_FIELDS = frozenset(
    {"name", "allowed_origins", "confidence_threshold", "daily_token_budget"}
)


@dataclass(frozen=True)
class WorkspaceRole:
    workspace_id: uuid.UUID
    name: str
    role: Role


@dataclass(frozen=True)
class Member:
    user_id: uuid.UUID
    email: str
    role: Role
    joined_at: datetime


def _new_public_key() -> str:
    return f"wk_live_{secrets.token_urlsafe(24)}"


async def create_workspace(session: AsyncSession, *, owner_id: uuid.UUID, name: str) -> Workspace:
    """Create a workspace and make ``owner_id`` its first owner, atomically."""
    workspace = Workspace(
        id=uuid.uuid4(),
        name=name,
        public_key=_new_public_key(),
        allowed_origins=[],
        confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
        daily_token_budget=DEFAULT_DAILY_TOKEN_BUDGET,
    )
    # The creator has no membership yet, so the context is bound to the new, still-empty workspace.
    # The database only allows the first owner row to be written by that same user.
    await bind_workspace(session, workspace.id)
    session.add(workspace)
    await session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=owner_id, role=Role.OWNER))
    await session.flush()
    return workspace


async def get_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found.")
    return workspace


async def update_workspace(
    session: AsyncSession, workspace_id: uuid.UUID, *, changes: Mapping[str, Any]
) -> Workspace:
    unknown = set(changes) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"fields cannot be updated: {sorted(unknown)}")

    workspace = await get_workspace(session, workspace_id)
    for field, value in changes.items():
        setattr(workspace, field, value)
    try:
        await session.flush()
    except StaleDataError as exc:
        # The UPDATE matched no row: the database policy only lets owners change a workspace.
        raise ForbiddenError("Only a workspace owner can change settings.") from exc
    return workspace


async def get_membership_role(
    session: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> Role | None:
    role = await session.scalar(
        select(Membership.role).where(
            Membership.user_id == user_id, Membership.workspace_id == workspace_id
        )
    )
    return Role(role) if role is not None else None


async def list_workspaces_for_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[WorkspaceRole]:
    result = await session.execute(
        select(Workspace.id, Workspace.name, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id)
        .order_by(Workspace.name)
    )
    return [WorkspaceRole(workspace_id, name, Role(role)) for workspace_id, name, role in result]


async def list_members(session: AsyncSession, *, workspace_id: uuid.UUID) -> list[Member]:
    result = await session.execute(
        select(Membership.user_id, User.email, Membership.role, Membership.created_at)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(Membership.created_at)
    )
    return [
        Member(user_id, email, Role(role), joined_at) for user_id, email, role, joined_at in result
    ]
