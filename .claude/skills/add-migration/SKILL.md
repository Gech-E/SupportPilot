---
name: add-migration
description: Add an Alembic migration for a new table, column, index, or row-level security policy in SupportPilot. Use whenever the database schema changes, especially for any tenant-owned table.
---

# Add a database migration

Migrations are append-only. Never edit a migration that is already merged.

## 1. Create the file
- New file in `services/api/migrations/versions/` named `NNNN_short_description.py`
  (next number). Set `down_revision` to the current head (`alembic heads`).
- Write SQL explicitly with `op.execute(...)`. Provide a working `downgrade()`.

## 2. If the table is tenant-owned (has `workspace_id`)
All of these are required, in the same migration:
1. `workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`
2. `ALTER TABLE t ENABLE ROW LEVEL SECURITY;` **and** `ALTER TABLE t FORCE ROW LEVEL SECURITY;`
3. One policy per command (SELECT, INSERT, UPDATE, DELETE) using `app_workspace_id()`:
   ```sql
   CREATE POLICY t_select ON t FOR SELECT USING (workspace_id = app_workspace_id());
   CREATE POLICY t_insert ON t FOR INSERT WITH CHECK (workspace_id = app_workspace_id());
   CREATE POLICY t_update ON t FOR UPDATE USING (workspace_id = app_workspace_id())
     WITH CHECK (workspace_id = app_workspace_id());
   CREATE POLICY t_delete ON t FOR DELETE USING (workspace_id = app_workspace_id());
   ```
   Omit a command's policy only if the app must never perform it (no policy means denied).
4. Least-privilege grants to `supportpilot_app`, only the commands the app needs:
   `GRANT SELECT, INSERT, UPDATE ON t TO supportpilot_app;`
5. An index starting with `workspace_id` for common queries.

## 3. Constraints
- Prefer database constraints (`CHECK`, `UNIQUE`, `FOREIGN KEY`) over trusting application code.
- Store enums as `text` with a `CHECK (col IN (...))`; they are easier to migrate than PG enums.
- Add `created_at timestamptz NOT NULL DEFAULT now()` to every table.

## 4. Update code and tests
- Add or update the SQLAlchemy model in `app/models/`.
- Add isolation cases to `tests/integration/test_rls.py` for the new table.
  The generic test `test_every_workspace_table_forces_rls` fails if you forget step 2.

## 5. Verify
```bash
make test            # runs alembic upgrade head on a fresh database
```
Also test the downgrade once locally: `alembic downgrade -1 && alembic upgrade head`.

## Zero-downtime rule
Use expand then contract: add nullable columns or new tables first, deploy code that works with both,
backfill, then tighten constraints in a later migration. Never drop or rename a column in the same
release that stops using it.
