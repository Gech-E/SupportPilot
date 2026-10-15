---
name: add-endpoint
description: Add or change a SupportPilot API route following the project's layering, authorization, error, and testing conventions. Use for any new or modified endpoint under services/api.
---

# Add an API endpoint

Follow these steps in order. Read `services/api/CLAUDE.md` first if you have not this session.

## 1. Decide the contract
- Path under `/api/v1`, plural noun, HTTP method, status code, who may call it (anonymous, any
  signed-in user, workspace member, workspace owner).
- Write request and response models in `app/schemas/`. Constrain every field: `min_length`,
  `max_length`, ranges, enums. Use `SecretStr` for secrets. Never return `password_hash` or tokens.

## 2. Put logic in a service
- Add a function to `app/services/<area>.py`. Signature: `async def name(session: AsyncSession, ...)`.
- Raise `NotFoundError`, `ForbiddenError`, `ConflictError` from `app/core/errors.py`. Never raise
  `HTTPException` in services.
- Use SQLAlchemy `select()`/`insert()` with bound values. No f-string SQL.

## 3. Write the thin router
- File: `app/api/routers/<area>.py`. Parse input, call the service, `await session.commit()` for
  mutations, return the schema.
- Authorization through dependencies, never inline checks:
  - signed-in user: `Depends(get_current_user)`
  - workspace member: `Depends(get_workspace_access)`
  - owner only: `Depends(require_owner)`
- Mutating cookie-authenticated routes also depend on `verify_csrf`.
- Another tenant's resource returns **404**, not 403.
- Register the router in `app/main.py` only if it is new.

## 4. Test it
- Integration test in `tests/integration/test_<area>_api.py` covering: happy path, validation
  failure (422), unauthenticated (401), wrong role (403), other tenant (404), and any conflict.
- If you touched tenant data access, confirm `tests/integration/test_rls.py` still passes.

## 5. Verify
```bash
make lint && make typecheck && make test
```
Then apply the `security-review` skill to the diff.

## Common mistakes to avoid
- Setting the workspace RLS context from a path parameter before verifying membership.
- Committing twice in one request (the RLS context is transaction-local and resets on commit).
- Returning raw exception text or SQL errors to the client.
- Logging request bodies.
