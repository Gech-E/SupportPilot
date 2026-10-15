"""Row-level security tests: the database itself must enforce tenant isolation.

These connect as the restricted ``supportpilot_app`` role and talk to PostgreSQL directly, with no
API in between. They prove isolation holds even if application code forgets a filter.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import pytest

from tests.integration.conftest import APP_ROLE, DatabaseUrls

ALICE = uuid.uuid4()
BOB = uuid.uuid4()
WORKSPACE_A = uuid.uuid4()
WORKSPACE_B = uuid.uuid4()


@pytest.fixture
async def app_pool(database_urls: DatabaseUrls) -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(database_urls.app_dsn, min_size=1, max_size=3)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture(autouse=True)
async def two_tenants(admin_connection: asyncpg.Connection, clean_database: None) -> None:
    """Alice owns workspace A, Bob owns workspace B. Arranged as superuser, outside RLS.

    Depends on ``clean_database`` explicitly so the tables are always emptied first.
    """
    for user_id, email in ((ALICE, "alice@example.com"), (BOB, "bob@example.com")):
        await admin_connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, 'x')", user_id, email
        )
    for workspace_id, name, key in (
        (WORKSPACE_A, "Workspace A", "wk_a"),
        (WORKSPACE_B, "Workspace B", "wk_b"),
    ):
        await admin_connection.execute(
            "INSERT INTO workspaces (id, name, public_key) VALUES ($1, $2, $3)",
            workspace_id,
            name,
            key,
        )
    for workspace_id, user_id in ((WORKSPACE_A, ALICE), (WORKSPACE_B, BOB)):
        await admin_connection.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
            workspace_id,
            user_id,
        )


@asynccontextmanager
async def as_app(
    pool: asyncpg.Pool, *, user: uuid.UUID | None = None, workspace: uuid.UUID | None = None
) -> AsyncIterator[asyncpg.Connection]:
    """A transaction as the app role with the given RLS context. Always rolled back."""
    async with pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            if user is not None:
                await connection.execute("SELECT set_config('app.user_id', $1, true)", str(user))
            if workspace is not None:
                await connection.execute(
                    "SELECT set_config('app.workspace_id', $1, true)", str(workspace)
                )
            yield connection
        finally:
            await transaction.rollback()


async def test_the_app_role_cannot_bypass_row_level_security(
    admin_connection: asyncpg.Connection,
) -> None:
    role = await admin_connection.fetchrow(
        "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
        "FROM pg_roles WHERE rolname = $1",
        APP_ROLE,
    )
    assert role is not None
    assert not any(role.values())


async def test_every_tenant_table_forces_row_level_security(
    admin_connection: asyncpg.Connection,
) -> None:
    """Fails when someone adds a table with workspace_id (or any table) without forced RLS."""
    unprotected = await admin_connection.fetch(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND c.relname NOT IN ('alembic_version', 'users')
          AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
        """
    )
    assert [row["relname"] for row in unprotected] == []


async def test_no_context_means_no_rows(app_pool: asyncpg.Pool) -> None:
    async with as_app(app_pool) as connection:
        assert await connection.fetch("SELECT 1 FROM workspaces") == []
        assert await connection.fetch("SELECT 1 FROM memberships") == []


async def test_workspace_context_shows_only_that_workspace(app_pool: asyncpg.Pool) -> None:
    async with as_app(app_pool, workspace=WORKSPACE_A) as connection:
        workspaces = await connection.fetch("SELECT id FROM workspaces")
        memberships = await connection.fetch("SELECT workspace_id, user_id FROM memberships")

    assert [row["id"] for row in workspaces] == [WORKSPACE_A]
    assert [(row["workspace_id"], row["user_id"]) for row in memberships] == [(WORKSPACE_A, ALICE)]


async def test_a_user_sees_only_their_own_memberships_and_workspaces(
    app_pool: asyncpg.Pool,
) -> None:
    async with as_app(app_pool, user=BOB) as connection:
        memberships = await connection.fetch("SELECT workspace_id FROM memberships")
        workspaces = await connection.fetch("SELECT id FROM workspaces")

    assert [row["workspace_id"] for row in memberships] == [WORKSPACE_B]
    assert [row["id"] for row in workspaces] == [WORKSPACE_B]


async def test_a_forged_workspace_id_in_a_query_returns_nothing(app_pool: asyncpg.Pool) -> None:
    """Even a WHERE clause naming another tenant's id cannot reach its rows."""
    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        rows = await connection.fetch("SELECT * FROM workspaces WHERE id = $1", WORKSPACE_B)
        members = await connection.fetch(
            "SELECT * FROM memberships WHERE workspace_id = $1", WORKSPACE_B
        )

    assert rows == []
    assert members == []


async def test_a_malformed_context_value_fails_closed(app_pool: asyncpg.Pool) -> None:
    async with app_pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute("SELECT set_config('app.workspace_id', 'not-a-uuid', true)")
            with pytest.raises(asyncpg.DataError):
                await connection.fetch("SELECT 1 FROM workspaces")
        finally:
            await transaction.rollback()


async def test_context_does_not_leak_across_transactions(app_pool: asyncpg.Pool) -> None:
    async with app_pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.workspace_id', $1, true)", str(WORKSPACE_A)
            )
            assert len(await connection.fetch("SELECT 1 FROM workspaces")) == 1
        # Same pooled connection, new transaction: the previous context must be gone.
        assert await connection.fetch("SELECT 1 FROM workspaces") == []


async def test_cannot_insert_a_membership_into_a_workspace_outside_the_context(
    app_pool: asyncpg.Pool,
) -> None:
    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
                WORKSPACE_B,
                ALICE,
            )


async def test_an_agent_cannot_add_members(
    app_pool: asyncpg.Pool, admin_connection: asyncpg.Connection
) -> None:
    agent = uuid.uuid4()
    await admin_connection.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, 'agent@example.com', 'x')", agent
    )
    await admin_connection.execute(
        "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
        WORKSPACE_A,
        agent,
    )

    async with as_app(app_pool, user=agent, workspace=WORKSPACE_A) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
                WORKSPACE_A,
                agent,
            )


async def test_an_owner_can_add_a_member(
    app_pool: asyncpg.Pool, admin_connection: asyncpg.Connection
) -> None:
    newcomer = uuid.uuid4()
    await admin_connection.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, 'new@example.com', 'x')",
        newcomer,
    )

    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        await connection.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
            WORKSPACE_A,
            newcomer,
        )
        count = await connection.fetchval("SELECT count(*) FROM memberships")

    assert count == 2


async def test_a_user_cannot_claim_ownership_of_an_existing_workspace(
    app_pool: asyncpg.Pool,
) -> None:
    """The bootstrap exception only applies to a workspace with no members at all."""
    async with as_app(app_pool, user=BOB, workspace=WORKSPACE_A) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
                WORKSPACE_A,
                BOB,
            )


async def test_a_new_workspace_can_be_bootstrapped_by_its_creator(
    app_pool: asyncpg.Pool,
) -> None:
    new_workspace = uuid.uuid4()
    async with as_app(app_pool, user=ALICE, workspace=new_workspace) as connection:
        await connection.execute(
            "INSERT INTO workspaces (id, name, public_key) VALUES ($1, 'Fresh', 'wk_fresh')",
            new_workspace,
        )
        await connection.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
            new_workspace,
            ALICE,
        )
        assert await connection.fetchval("SELECT count(*) FROM workspaces") == 2  # A and Fresh


async def test_creator_cannot_bootstrap_someone_else_as_owner(app_pool: asyncpg.Pool) -> None:
    new_workspace = uuid.uuid4()
    async with as_app(app_pool, user=ALICE, workspace=new_workspace) as connection:
        await connection.execute(
            "INSERT INTO workspaces (id, name, public_key) VALUES ($1, 'Fresh', 'wk_fresh')",
            new_workspace,
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
                new_workspace,
                BOB,
            )


async def test_only_an_owner_can_update_a_workspace(
    app_pool: asyncpg.Pool, admin_connection: asyncpg.Connection
) -> None:
    agent = uuid.uuid4()
    await admin_connection.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, 'agent@example.com', 'x')", agent
    )
    await admin_connection.execute(
        "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
        WORKSPACE_A,
        agent,
    )

    async with as_app(app_pool, user=agent, workspace=WORKSPACE_A) as connection:
        result = await connection.execute("UPDATE workspaces SET name = 'Hijacked'")
    assert result == "UPDATE 0"  # the policy hides the row from UPDATE, so nothing changes

    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        result = await connection.execute("UPDATE workspaces SET name = 'Renamed'")
    assert result == "UPDATE 1"


async def test_an_update_cannot_touch_another_workspace(app_pool: asyncpg.Pool) -> None:
    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        result = await connection.execute(
            "UPDATE workspaces SET name = 'Hijacked' WHERE id = $1", WORKSPACE_B
        )
    assert result == "UPDATE 0"


async def test_deleting_is_not_permitted_for_the_app_role(app_pool: asyncpg.Pool) -> None:
    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("DELETE FROM workspaces")
    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("DELETE FROM memberships")


async def test_users_cannot_be_listed_without_a_context(app_pool: asyncpg.Pool) -> None:
    """A bug or injection in the API role must not be able to dump accounts or password hashes."""
    async with as_app(app_pool) as connection:
        assert await connection.fetch("SELECT email, password_hash FROM users") == []


async def test_a_user_sees_only_themselves_and_their_workspace_members(
    app_pool: asyncpg.Pool, admin_connection: asyncpg.Connection
) -> None:
    colleague = uuid.uuid4()
    await admin_connection.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, 'colleague@example.com', 'x')",
        colleague,
    )
    await admin_connection.execute(
        "INSERT INTO memberships (workspace_id, user_id, role) VALUES ($1, $2, 'agent')",
        WORKSPACE_A,
        colleague,
    )

    async with as_app(app_pool, user=ALICE) as connection:
        alone = {row["email"] for row in await connection.fetch("SELECT email FROM users")}
    async with as_app(app_pool, user=ALICE, workspace=WORKSPACE_A) as connection:
        together = {row["email"] for row in await connection.fetch("SELECT email FROM users")}

    assert alone == {"alice@example.com"}
    assert together == {"alice@example.com", "colleague@example.com"}  # never bob@example.com


async def test_the_app_role_cannot_alter_or_delete_users(app_pool: asyncpg.Pool) -> None:
    async with as_app(app_pool, user=ALICE) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("UPDATE users SET is_active = false")
    async with as_app(app_pool, user=ALICE) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("DELETE FROM users")


async def test_login_lookup_returns_one_exact_match_without_any_context(
    app_pool: asyncpg.Pool,
) -> None:
    async with as_app(app_pool) as connection:
        found = await connection.fetch(
            "SELECT id, password_hash, is_active FROM auth_find_user($1)", "alice@example.com"
        )
        missing = await connection.fetch("SELECT id FROM auth_find_user($1)", "nobody@example.com")
        wildcard = await connection.fetch("SELECT id FROM auth_find_user($1)", "%@example.com")

    assert [row["id"] for row in found] == [ALICE]
    assert missing == []
    assert wildcard == []  # exact match only, so it cannot be used to enumerate accounts


async def test_login_lookup_is_not_callable_by_other_roles(
    admin_connection: asyncpg.Connection,
) -> None:
    """EXECUTE was revoked from PUBLIC; only the app role (and the owner) may call it."""
    privileged = await admin_connection.fetch(
        """
        SELECT grantee FROM information_schema.routine_privileges
        WHERE routine_name = 'auth_find_user' AND privilege_type = 'EXECUTE'
        """
    )
    current_user = await admin_connection.fetchval("SELECT current_user")
    assert {row["grantee"] for row in privileged} <= {APP_ROLE, "postgres", current_user}


async def test_documents_and_chunks_are_isolated_by_workspace(
    admin_connection: asyncpg.Connection, app_pool: asyncpg.Pool
) -> None:
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    await admin_connection.execute(
        "INSERT INTO documents (id, workspace_id, filename, content_type, size_bytes, status) "
        "VALUES ($1, $2, 'doc_a.txt', 'text/plain', 100, 'indexed')",
        doc_a,
        WORKSPACE_A,
    )
    await admin_connection.execute(
        "INSERT INTO documents (id, workspace_id, filename, content_type, size_bytes, status) "
        "VALUES ($1, $2, 'doc_b.txt', 'text/plain', 200, 'indexed')",
        doc_b,
        WORKSPACE_B,
    )
    vec = "[" + ",".join(["0.1"] * 1536) + "]"
    await admin_connection.execute(
        "INSERT INTO document_chunks "
        "(workspace_id, document_id, chunk_index, content, token_count, embedding) "
        "VALUES ($1, $2, 0, 'Chunk A content', 10, $3::vector)",
        WORKSPACE_A,
        doc_a,
        vec,
    )
    await admin_connection.execute(
        "INSERT INTO document_chunks "
        "(workspace_id, document_id, chunk_index, content, token_count, embedding) "
        "VALUES ($1, $2, 0, 'Chunk B content', 10, $3::vector)",
        WORKSPACE_B,
        doc_b,
        vec,
    )

    async with as_app(app_pool) as connection:
        assert await connection.fetch("SELECT id FROM documents") == []
        assert await connection.fetch("SELECT id FROM document_chunks") == []

    async with as_app(app_pool, workspace=WORKSPACE_A) as connection:
        docs_a = await connection.fetch("SELECT id FROM documents")
        chunks_a = await connection.fetch("SELECT document_id FROM document_chunks")
        assert [r["id"] for r in docs_a] == [doc_a]
        assert [r["document_id"] for r in chunks_a] == [doc_a]

    async with as_app(app_pool, workspace=WORKSPACE_B) as connection:
        docs_b = await connection.fetch("SELECT id FROM documents")
        chunks_b = await connection.fetch("SELECT document_id FROM document_chunks")
        assert [r["id"] for r in docs_b] == [doc_b]
        assert [r["document_id"] for r in chunks_b] == [doc_b]


async def test_cannot_insert_or_modify_document_for_another_workspace(
    admin_connection: asyncpg.Connection, app_pool: asyncpg.Pool
) -> None:
    doc_b = uuid.uuid4()
    await admin_connection.execute(
        "INSERT INTO documents (id, workspace_id, filename, content_type, size_bytes, status) "
        "VALUES ($1, $2, 'doc_b.txt', 'text/plain', 200, 'indexed')",
        doc_b,
        WORKSPACE_B,
    )

    async with as_app(app_pool, workspace=WORKSPACE_A) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO documents (workspace_id, filename, content_type, size_bytes, status) "
                "VALUES ($1, 'forged.txt', 'text/plain', 100, 'pending')",
                WORKSPACE_B,
            )

    async with as_app(app_pool, workspace=WORKSPACE_A) as connection:
        result = await connection.execute(
            "UPDATE documents SET filename = 'hacked.txt' WHERE id = $1", doc_b
        )
        assert result == "UPDATE 0"

    async with as_app(app_pool, workspace=WORKSPACE_A) as connection:
        result = await connection.execute("DELETE FROM documents WHERE id = $1", doc_b)
        assert result == "DELETE 0"
