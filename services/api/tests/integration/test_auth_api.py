from collections.abc import Callable

import asyncpg
from httpx import AsyncClient

from tests.integration.helpers import PASSWORD, csrf_headers, signup


def _cookie_header(response_headers: list[str], name: str) -> str:
    return next(header for header in response_headers if header.startswith(f"{name}="))


async def test_signup_creates_an_account_and_starts_a_session(client: AsyncClient) -> None:
    response = await signup(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert set(body) == {"id", "email"}  # never the password or its hash

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "alice@example.com"
    assert me.json()["workspaces"] == []


async def test_session_cookies_have_the_expected_security_flags(client: AsyncClient) -> None:
    response = await signup(client)
    cookies = response.headers.get_list("set-cookie")

    session_cookie = _cookie_header(cookies, "sp_session").lower()
    assert "httponly" in session_cookie
    assert "secure" in session_cookie
    assert "samesite=lax" in session_cookie
    assert "max-age=" in session_cookie

    csrf_cookie = _cookie_header(cookies, "sp_csrf").lower()
    assert "httponly" not in csrf_cookie  # the dashboard must be able to read it
    assert "secure" in csrf_cookie
    assert "samesite=lax" in csrf_cookie


async def test_email_uniqueness_ignores_case(client: AsyncClient) -> None:
    assert (await signup(client, "alice@example.com")).status_code == 201

    duplicate = await signup(client, "ALICE@Example.com")

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_taken"


async def test_weak_password_is_rejected_and_never_echoed(client: AsyncClient) -> None:
    response = await signup(client, password="hunter2")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "hunter2" not in response.text


async def test_login_succeeds_with_correct_credentials(
    client_factory: Callable[[], AsyncClient],
) -> None:
    await signup(client_factory())

    fresh_client = client_factory()
    response = await fresh_client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert (await fresh_client.get("/api/v1/me")).status_code == 200


async def test_wrong_password_and_unknown_email_are_indistinguishable(
    client_factory: Callable[[], AsyncClient],
) -> None:
    await signup(client_factory())
    client = client_factory()

    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "not the password"}
    )
    unknown_email = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "not the password"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    wrong_error = wrong_password.json()["error"]
    unknown_error = unknown_email.json()["error"]
    assert wrong_error["code"] == unknown_error["code"] == "invalid_credentials"
    assert wrong_error["message"] == unknown_error["message"]


async def test_repeated_failed_logins_are_rate_limited(client: AsyncClient) -> None:
    attempt = {"email": "alice@example.com", "password": "wrong password"}
    for _ in range(3):  # login_max_attempts is 3 in the test settings
        assert (await client.post("/api/v1/auth/login", json=attempt)).status_code == 401

    blocked = await client.post("/api/v1/auth/login", json=attempt)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_garbage_session_cookie_is_rejected(client: AsyncClient) -> None:
    client.cookies.set("sp_session", "not-a-real-token")

    assert (await client.get("/api/v1/me")).status_code == 401


async def test_logout_requires_csrf_and_ends_the_session(client: AsyncClient) -> None:
    await signup(client)

    without_csrf = await client.post("/api/v1/auth/logout")
    assert without_csrf.status_code == 403
    assert without_csrf.json()["error"]["code"] == "csrf_failed"

    wrong_csrf = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "forged"})
    assert wrong_csrf.status_code == 403

    logout = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logout.status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_deactivated_user_loses_access(
    client_factory: Callable[[], AsyncClient], admin_connection: asyncpg.Connection
) -> None:
    client = client_factory()
    await signup(client)
    await admin_connection.execute("UPDATE users SET is_active = false")

    assert (await client.get("/api/v1/me")).status_code == 401
    login = await client_factory().post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401


async def test_error_responses_carry_the_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me", headers={"X-Request-Id": "trace-id-12345"})

    assert response.headers["x-request-id"] == "trace-id-12345"
    assert response.json()["error"]["request_id"] == "trace-id-12345"


async def test_readiness_reports_a_working_database(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
