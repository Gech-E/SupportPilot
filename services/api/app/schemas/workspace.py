import re
import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.workspace import Role
from app.schemas.auth import UserOut

# An origin is scheme + host (+ port) and nothing else. No paths, queries, or wildcards.
_ORIGIN_PATTERN = re.compile(r"^https?://[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$")
_MAX_ALLOWED_ORIGINS = 20


def _normalise_origin(value: str) -> str:
    origin = value.strip().lower()
    if not _ORIGIN_PATTERN.fullmatch(origin):
        raise ValueError(f"{value!r} is not an origin; use the form https://example.com")
    return origin


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)


class WorkspaceUpdate(BaseModel):
    """Partial update. Omitted fields are unchanged; explicit nulls are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
    allowed_origins: list[str] | None = Field(default=None, max_length=_MAX_ALLOWED_ORIGINS)
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    daily_token_budget: int | None = Field(default=None, ge=1, le=10_000_000)

    @field_validator("allowed_origins")
    @classmethod
    def _normalise_origins(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalised = [_normalise_origin(origin) for origin in value]
        return list(dict.fromkeys(normalised))  # drop duplicates, keep order

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    public_key: str
    allowed_origins: list[str]
    confidence_threshold: float
    daily_token_budget: int
    created_at: datetime


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    role: Role
    joined_at: datetime


class MeOut(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceSummary]
