# ADR 0001: Enforce tenant isolation with PostgreSQL row-level security

Status: accepted (milestone 1)

## Context
Every workspace's documents, conversations and credentials must be invisible to every other
workspace. A single forgotten `WHERE workspace_id = ...` in application code would leak data.

## Decision
- Tenant tables have row-level security **enabled and forced**, so even the table owner is subject
  to the policies.
- The API connects as `supportpilot_app`: no ownership, no `BYPASSRLS`, no superuser. Migrations use a
  separate owner role.
- Per request, inside the transaction, the API sets `app.user_id` (after the session cookie is
  verified) and `app.workspace_id` (only **after** membership is verified) with
  `set_config(..., true)`, which is transaction-local.
- Policies read those settings through `app_user_id()` and `app_workspace_id()`. An unset setting is
  `NULL`, which never equals anything, so the default is deny.
- Policies are written per command. Commands with no policy (DELETE, and UPDATE on memberships) are
  denied until a feature needs them and adds a reviewed policy.
- `users` is global, not tenant-owned. RLS is enabled but not forced, and login uses a narrow
  `SECURITY DEFINER` function `auth_find_user(email)`; the app role cannot read `password_hash` any
  other way.

## Alternatives considered
- **Application-level filters only.** Simple, but one mistake leaks data and nothing catches it.
- **Schema per tenant.** Strong isolation, but migrations and connection handling grow with the
  number of tenants. Revisit if a customer needs per-tenant encryption keys or data residency.

## Consequences
- Isolation survives application bugs and is testable directly against the database.
- Committing ends the transaction and clears the context, so routes commit once at the end.
- A new tenant table must follow the `add-migration` skill. A test fails if forced RLS is missing.
- Small per-query overhead from policy evaluation; indexes start with `workspace_id`.
