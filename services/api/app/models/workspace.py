import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ARRAY, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

DEFAULT_CONFIDENCE_THRESHOLD = 0.55
DEFAULT_DAILY_TOKEN_BUDGET = 500_000


class Role(StrEnum):
    OWNER = "owner"
    AGENT = "agent"


class Workspace(Base):
    """The tenant. Everything a business owns hangs off a workspace."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    # Identifies the widget. Public by design: it grants no access without an allowed origin.
    public_key: Mapped[str]
    allowed_origins: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    confidence_threshold: Mapped[float] = mapped_column(default=DEFAULT_CONFIDENCE_THRESHOLD)
    daily_token_budget: Mapped[int] = mapped_column(default=DEFAULT_DAILY_TOKEN_BUDGET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str]  # a Role value; the database CHECK constraint is the source of truth
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
