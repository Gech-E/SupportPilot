"""Session cookie handling.

Two cookies are issued:
* ``sp_session``  the signed session token. HttpOnly, so scripts cannot read it.
* ``sp_csrf``     a CSRF token bound to that session. Readable by the dashboard so it can echo the
                  value in the ``X-CSRF-Token`` header on state-changing requests.
Both are SameSite=Lax and Secure outside local development.
"""

import uuid
from datetime import timedelta

from fastapi import Response

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE
from app.core.config import Settings
from app.core.tokens import create_session_token, csrf_token_for


def start_session(response: Response, user_id: uuid.UUID, settings: Settings) -> None:
    ttl = timedelta(minutes=settings.session_ttl_minutes)
    secret = settings.session_secret.get_secret_value()
    token = create_session_token(user_id, secret=secret, ttl=ttl)
    max_age = int(ttl.total_seconds())

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token_for(token, secret=secret),
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def end_session(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", httponly=False, secure=settings.cookie_secure, samesite="lax"
    )
