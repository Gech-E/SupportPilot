from collections.abc import Callable

import asyncpg
from httpx import AsyncClient

from tests.integration.helpers import create_workspace, csrf_headers, signup


async def test_creating_a_workspace_makes_the_creator_its_owner(client: AsyncClient) -> None:
    await signup(client)

    workspace = await create_workspace(client, "Acme Bakery")

    assert workspace["name"] == "Acme Bakery"
    assert workspace["public_key"].startswith("wk_live_")
    assert workspace["allowed_origins"] == []
    assert workspace["confidence_threshold"] == 0.55
    me = await client.get("/api/v1/me")
    assert me.json()["workspaces"] == [
        {"id": workspace["id"], "name": "Acme Bakery", "role": "owner"}
    ]


async def test_state_changing_requests_need_a_csrf_header(client: AsyncClient) -> None:
    await signup(client)

    response = await client.post("/api/v1/workspaces", json={"name": "Acme"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_workspace_routes_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/workspaces/3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90")

    assert response.status_code == 401


async def test_a_member_can_read_their_workspace(client: AsyncClient) -> None:
    await signup(client)
    workspace = await create_workspace(client)

    response = await client.get(f"/api/v1/workspaces/{workspace['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == workspace["id"]


async def test_another_tenants_workspace_looks_like_it_does_not_exist(
    client_factory: Callable[[], AsyncClient],
) -> None:
    alice, mallory = client_factory(), client_factory()
    await signup(alice, "alice@example.com")
    await signup(mallory, "mallory@example.com")
    workspace = await create_workspace(alice)
    path = f"/api/v1/workspaces/{workspace['id']}"

    assert (await mallory.get(path)).status_code == 404
    assert (await mallory.get(f"{path}/members")).status_code == 404
    patch = await mallory.patch(path, json={"name": "Hijacked"}, headers=csrf_headers(mallory))
    assert patch.status_code == 404

    unchanged = await alice.get(path)
    assert unchanged.json()["name"] == "Acme Bakery"


async def test_an_owner_can_update_settings(client: AsyncClient) -> None:
    await signup(client)
    workspace = await create_workspace(client)

    response = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}",
        json={
            "name": "Acme Bakery Ltd",
            "allowed_origins": ["HTTPS://Shop.Example.com", "https://shop.example.com"],
            "confidence_threshold": 0.7,
            "daily_token_budget": 100000,
        },
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Acme Bakery Ltd"
    assert updated["allowed_origins"] == ["https://shop.example.com"]
    assert updated["confidence_threshold"] == 0.7
    assert updated["daily_token_budget"] == 100000

    persisted = (await client.get(f"/api/v1/workspaces/{workspace['id']}")).json()
    assert persisted == updated


async def test_an_agent_can_read_but_not_change_the_workspace(
    client_factory: Callable[[], AsyncClient], admin_connection: asyncpg.Connection
) -> None:
    owner, agent = client_factory(), client_factory()
    await signup(owner, "owner@example.com")
    agent_user = (await signup(agent, "agent@example.com")).json()
    workspace = await create_workspace(owner)
    await admin_connection.execute(
        "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
        workspace["id"],
        agent_user["id"],
    )
    path = f"/api/v1/workspaces/{workspace['id']}"

    assert (await agent.get(path)).status_code == 200
    patch = await agent.patch(path, json={"name": "Nope"}, headers=csrf_headers(agent))
    assert patch.status_code == 403
    assert patch.json()["error"]["code"] == "forbidden"
    assert (await owner.get(path)).json()["name"] == "Acme Bakery"


async def test_invalid_updates_are_rejected(client: AsyncClient) -> None:
    await signup(client)
    workspace = await create_workspace(client)
    path = f"/api/v1/workspaces/{workspace['id']}"
    headers = csrf_headers(client)

    bad_bodies = [
        {"confidence_threshold": 1.5},
        {"daily_token_budget": 0},
        {"name": None},
        {"allowed_origins": ["https://example.com/path"]},
        {"allowed_origins": ["*"]},
        {"public_key": "wk_live_chosen_by_attacker"},  # not an updatable field
        {"id": "00000000-0000-0000-0000-000000000000"},
    ]
    for body in bad_bodies:
        response = await client.patch(path, json=body, headers=headers)
        assert response.status_code == 422, body
        assert response.json()["error"]["code"] == "validation_error"


async def test_members_endpoint_lists_owner_and_agent(
    client_factory: Callable[[], AsyncClient], admin_connection: asyncpg.Connection
) -> None:
    owner, agent = client_factory(), client_factory()
    await signup(owner, "owner@example.com")
    agent_user = (await signup(agent, "agent@example.com")).json()
    workspace = await create_workspace(owner)
    await admin_connection.execute(
        "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
        workspace["id"],
        agent_user["id"],
    )

    response = await agent.get(f"/api/v1/workspaces/{workspace['id']}/members")

    assert response.status_code == 200
    members = {member["email"]: member["role"] for member in response.json()}
    assert members == {"owner@example.com": "owner", "agent@example.com": "agent"}


async def test_malformed_workspace_id_is_a_validation_error(client: AsyncClient) -> None:
    await signup(client)

    response = await client.get("/api/v1/workspaces/not-a-uuid")

    assert response.status_code == 422


async def test_each_user_only_sees_their_own_workspaces(
    client_factory: Callable[[], AsyncClient],
) -> None:
    alice, bob = client_factory(), client_factory()
    await signup(alice, "alice@example.com")
    await signup(bob, "bob@example.com")
    await create_workspace(alice, "Alice Co")
    await create_workspace(bob, "Bob Co")

    alice_me = (await alice.get("/api/v1/me")).json()
    bob_me = (await bob.get("/api/v1/me")).json()

    assert [item["name"] for item in alice_me["workspaces"]] == ["Alice Co"]
    assert [item["name"] for item in bob_me["workspaces"]] == ["Bob Co"]
