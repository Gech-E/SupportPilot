"""Session tokens and CSRF tokens.

Pure functions: the secret and lifetime are passed in, so they are easy to test and the module has
no dependency on application settings.
"""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

import jwt

_ALGORITHM = "HS256"
_ISSUER = "supportpilot"
_REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss"]
# Domain separation: a CSRF value can never be confused with a JWT signature.
_CSRF_CONTEXT = b"supportpilot-csrf-v1:"


class InvalidTokenError(Exception):
    """The session token is missing required claims, expired, tampered with, or malformed."""


def create_session_token(
    user_id: uuid.UUID, *, secret: str, ttl: timedelta, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iss": _ISSUER,
        "iat": issued_at,
        "exp": issued_at + ttl,
    }
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def decode_session_token(token: str, *, secret: str) -> uuid.UUID:
    """Return the user id from a valid token, or raise ``InvalidTokenError``.

    The algorithm is pinned, so tokens signed with ``none`` or any other algorithm are rejected.
    """
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": _REQUIRED_CLAIMS},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError from exc


def csrf_token_for(session_token: str, *, secret: str) -> str:
    """Derive the CSRF token bound to one session token.

    Binding to the session means an attacker who can plant a cookie (for example from a sibling
    subdomain) still cannot produce a matching header value.
    """
    digest = hmac.new(
        secret.encode(), _CSRF_CONTEXT + session_token.encode(), hashlib.sha256
    ).hexdigest()
    return digest


def csrf_is_valid(session_token: str, supplied: str | None, *, secret: str) -> bool:
    if not supplied:
        return False
    expected = csrf_token_for(session_token, secret=secret)
    return hmac.compare_digest(expected.encode(), supplied.encode())
