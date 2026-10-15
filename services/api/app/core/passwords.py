"""Password hashing with Argon2id.

Hashing is deliberately slow and CPU-bound. Call these through ``asyncio.to_thread`` from async
code so they never block the event loop.
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Library defaults follow RFC 9106 recommendations (Argon2id, random per-hash salt).
_hasher = PasswordHasher()

# A valid hash of a random value. Verifying against it when an account does not exist keeps the
# response time of "unknown email" close to "wrong password", so timing does not reveal accounts.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(24))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return True only when the password matches. Never raises on bad input."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
