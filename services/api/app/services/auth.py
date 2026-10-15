"""Account registration and credential checks."""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnauthenticatedError
from app.core.passwords import DUMMY_HASH, hash_password, verify_password
from app.models.user import User

_EMAIL_UNIQUE_CONSTRAINT = "users_email_key"

# The only way the API role may read credentials (see migration 0001): row-level security hides
# the users table from it, and this SECURITY DEFINER function returns one exact-match account.
_FIND_CREDENTIALS = text("SELECT id, password_hash, is_active FROM auth_find_user(:email)")


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str


async def register_user(session: AsyncSession, *, email: str, password: str) -> User:
    """Create an account. ``email`` must already be normalised to lowercase."""
    password_hash = await asyncio.to_thread(hash_password, password)
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Rely on the unique constraint rather than check-then-insert, which races.
        if _EMAIL_UNIQUE_CONSTRAINT in str(exc.orig):
            raise ConflictError(
                "An account with this email already exists.", code="email_taken"
            ) from exc
        raise
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> AuthenticatedUser:
    """Return the user for valid credentials, otherwise raise one uniform error.

    The hash is verified even when the account does not exist, so response timing does not reveal
    which emails are registered.
    """
    row = (await session.execute(_FIND_CREDENTIALS, {"email": email})).one_or_none()
    candidate_hash = row.password_hash if row is not None else DUMMY_HASH
    password_matches = await asyncio.to_thread(verify_password, candidate_hash, password)

    if row is None or not password_matches or not row.is_active:
        raise UnauthenticatedError("Invalid email or password.", code="invalid_credentials")
    return AuthenticatedUser(id=row.id, email=email)
