"""Initial schema: users, workspaces, memberships, with row-level security.

Tenant isolation is enforced by PostgreSQL, not only by application code:

* The API sets two transaction-local settings per request: ``app.user_id`` (always, once the
  session cookie is verified) and ``app.workspace_id`` (only after membership is verified).
* Every tenant table has RLS enabled *and forced*, so even the table owner is subject to policies.
* The API connects as ``supportpilot_app``, which owns nothing and cannot bypass RLS. That role is
  created by infra/postgres/init-roles.sh (or the test fixtures); this migration only grants to it.
* An unset or empty setting yields NULL, and ``x = NULL`` is never true, so the default is deny.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "supportpilot_app"

_STATEMENTS_UP = [
    # --- helpers that read the per-request context -------------------------------------------
    """
    CREATE FUNCTION app_user_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$
    """,
    """
    CREATE FUNCTION app_workspace_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.workspace_id', true), '')::uuid $$
    """,
    # --- users: global identities, not tenant-owned -------------------------------------------
    """
    CREATE TABLE users (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email text NOT NULL,
        password_hash text NOT NULL,
        is_active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT users_email_key UNIQUE (email),
        CONSTRAINT users_email_lowercase CHECK (email = lower(email)),
        CONSTRAINT users_email_length CHECK (char_length(email) BETWEEN 3 AND 254)
    )
    """,
    # --- workspaces: the tenant ---------------------------------------------------------------
    """
    CREATE TABLE workspaces (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        name text NOT NULL,
        public_key text NOT NULL,
        allowed_origins text[] NOT NULL DEFAULT '{}',
        confidence_threshold double precision NOT NULL DEFAULT 0.55,
        daily_token_budget integer NOT NULL DEFAULT 500000,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT workspaces_public_key_key UNIQUE (public_key),
        CONSTRAINT workspaces_name_length CHECK (char_length(name) BETWEEN 1 AND 80),
        CONSTRAINT workspaces_threshold_range CHECK (confidence_threshold BETWEEN 0 AND 1),
        CONSTRAINT workspaces_budget_positive CHECK (daily_token_budget > 0)
    )
    """,
    # --- memberships: who belongs to which workspace, with a role ------------------------------
    """
    CREATE TABLE memberships (
        workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        role text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (workspace_id, user_id),
        CONSTRAINT memberships_role_valid CHECK (role IN ('owner', 'agent'))
    )
    """,
    "CREATE INDEX memberships_user_idx ON memberships (user_id)",
    # --- RLS: users ----------------------------------------------------------------------------
    # Limits the blast radius of any bug or injection in the API role: it cannot list accounts or
    # read password hashes. ENABLE without FORCE on purpose: the table owner (which owns the
    # SECURITY DEFINER login function below) must be able to read the table.
    "ALTER TABLE users ENABLE ROW LEVEL SECURITY",
    # A user sees themselves, and the other members of the workspace currently in context.
    """
    CREATE POLICY users_select ON users FOR SELECT
        USING (
            id = app_user_id()
            OR id IN (SELECT m.user_id FROM memberships m WHERE m.workspace_id = app_workspace_id())
        )
    """,
    # Anyone may register; uniqueness is enforced by the email constraint.
    "CREATE POLICY users_insert ON users FOR INSERT WITH CHECK (true)",
    # Login must find an account by email *before* anyone is authenticated. This function is the
    # only way to do that: it returns one account's credentials for an exact email match, and the
    # app role has no other way to read ``password_hash``.
    """
    CREATE FUNCTION auth_find_user(p_email text)
    RETURNS TABLE (id uuid, password_hash text, is_active boolean)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = public, pg_temp
    AS $$
        SELECT u.id, u.password_hash, u.is_active FROM users u WHERE u.email = p_email
    $$
    """,
    "REVOKE ALL ON FUNCTION auth_find_user(text) FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION auth_find_user(text) TO {APP_ROLE}",
    # --- RLS: memberships ----------------------------------------------------------------------
    "ALTER TABLE memberships ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE memberships FORCE ROW LEVEL SECURITY",
    # A user can see their own memberships in any workspace (to list their workspaces), and every
    # membership of the workspace currently in context.
    """
    CREATE POLICY memberships_select ON memberships FOR SELECT
        USING (workspace_id = app_workspace_id() OR user_id = app_user_id())
    """,
    # Only an owner can add members. The one exception is bootstrapping: the creator becomes the
    # first owner of a workspace that has no members yet.
    """
    CREATE POLICY memberships_insert ON memberships FOR INSERT
        WITH CHECK (
            workspace_id = app_workspace_id()
            AND (
                EXISTS (
                    SELECT 1 FROM memberships o
                    WHERE o.workspace_id = app_workspace_id()
                      AND o.user_id = app_user_id()
                      AND o.role = 'owner'
                )
                OR (
                    user_id = app_user_id()
                    AND role = 'owner'
                    AND NOT EXISTS (
                        SELECT 1 FROM memberships e WHERE e.workspace_id = app_workspace_id()
                    )
                )
            )
        )
    """,
    # No UPDATE or DELETE policy on memberships: those commands are denied until a feature needs
    # them and adds a reviewed policy.
    # --- RLS: workspaces -----------------------------------------------------------------------
    "ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE workspaces FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY workspaces_select ON workspaces FOR SELECT
        USING (
            id = app_workspace_id()
            OR id IN (SELECT m.workspace_id FROM memberships m WHERE m.user_id = app_user_id())
        )
    """,
    "CREATE POLICY workspaces_insert ON workspaces FOR INSERT WITH CHECK (id = app_workspace_id())",
    # Only owners can change workspace settings, enforced here even if application code forgets.
    """
    CREATE POLICY workspaces_update ON workspaces FOR UPDATE
        USING (
            id = app_workspace_id()
            AND EXISTS (
                SELECT 1 FROM memberships m
                WHERE m.workspace_id = workspaces.id
                  AND m.user_id = app_user_id()
                  AND m.role = 'owner'
            )
        )
        WITH CHECK (id = app_workspace_id())
    """,
    # No DELETE policy on workspaces: deletion is a separate, reviewed feature.
    # --- least-privilege grants to the API role ------------------------------------------------
    f"GRANT SELECT, INSERT ON users TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE ON workspaces TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON memberships TO {APP_ROLE}",
    f"GRANT EXECUTE ON FUNCTION app_user_id(), app_workspace_id() TO {APP_ROLE}",
]

_STATEMENTS_DOWN = [
    "DROP FUNCTION auth_find_user(text)",
    # Policies on other tables read ``memberships``, so they must go before it can be dropped.
    "DROP POLICY users_select ON users",
    "DROP POLICY workspaces_select ON workspaces",
    "DROP POLICY workspaces_update ON workspaces",
    "DROP TABLE memberships",
    "DROP TABLE workspaces",
    "DROP TABLE users",
    "DROP FUNCTION app_workspace_id()",
    "DROP FUNCTION app_user_id()",
]


def upgrade() -> None:
    for statement in _STATEMENTS_UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _STATEMENTS_DOWN:
        op.execute(statement)
