from typing import Any

from httpx import AsyncClient, Response

PASSWORD = "correct horse battery staple"


async def signup(
    client: AsyncClient, email: str = "alice@example.com", password: str = PASSWORD
) -> Response:
    return await client.post("/api/v1/auth/signup", json={"email": email, "password": password})


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    """The header the dashboard sends: the readable CSRF cookie echoed back."""
    return {"X-CSRF-Token": client.cookies.get("sp_csrf") or ""}


async def create_workspace(client: AsyncClient, name: str = "Acme Bakery") -> dict[str, Any]:
    response = await client.post(
        "/api/v1/workspaces", json={"name": name}, headers=csrf_headers(client)
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created
