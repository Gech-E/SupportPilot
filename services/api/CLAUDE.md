# API service guide

Python 3.12+, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic v2, structlog.

## Layout and layering

```
app/
  main.py          app factory: wiring only (middleware, routers, handlers, lifespan)
  core/            cross-cutting: config, security, db, errors, logging, middleware, rate limiting
  models/          SQLAlchemy models. Data shape only, no business logic
  schemas/         Pydantic request/response models. The public API contract
  services/        business rules. Functions take an AsyncSession, return models or raise AppError
  api/deps.py      FastAPI dependencies: session, current user, workspace access, CSRF
  api/routers/     thin HTTP layer: parse, call a service, shape the response, set cookies
migrations/        Alembic (hand-written SQL for RLS). Append-only
tests/unit/        no database
tests/integration/ real PostgreSQL, app connects as the restricted role
```

Dependency direction is one way: `routers -> services -> models`, and everyone may use `core`.
Routers never contain business rules. Services never import FastAPI.

## How requests are handled

1. `RequestContextMiddleware` assigns a request id and adds security headers.
2. `get_current_user` verifies the session cookie, then sets `app.user_id` for the transaction.
3. `get_workspace_access` verifies membership **first**, and only then sets `app.workspace_id`.
   This order matters: the workspace context must never come from an unverified URL parameter.
4. The service runs queries. PostgreSQL RLS filters rows as a second line of defense.
5. The router calls `await session.commit()` once after mutations. `set_config(..., true)` is
   transaction-local, so after a commit the RLS context is gone and queries return nothing (safe default).

## Conventions

- Routes live under `/api/v1`. Resource names are plural nouns. Status codes: 201 create, 204 no body.
- Errors: raise `NotFoundError`, `ForbiddenError`, `ConflictError`, etc. Shape is always
  `{"error": {"code", "message", "request_id"}}`. Validation errors never echo submitted values.
- Mutating routes that use cookie auth depend on `verify_csrf`.
- Settings are read once through `get_settings()`; never read `os.environ` elsewhere.
- Emails are normalised to lowercase before storage and lookup.
- Passwords are `SecretStr` in schemas, hashed with Argon2id, and never logged.
- Use `select()` with bound values. No f-string SQL. Raw SQL belongs only in migrations.

## Testing

- Unit tests: pure functions (security, validation, config).
- Integration tests: `client` fixture talks to the real app over `https://testserver`
  (cookies are `Secure`), against a fresh database migrated by Alembic. The app uses the
  restricted `supportpilot_app` role, same as production.
- Every tenant table needs an isolation test in `tests/integration/test_rls.py`; the generic test
  there fails if a table with `workspace_id` lacks forced RLS.
- Run: `pytest -q`. Coverage target for `app/core` and `app/services`: 85%+.

## Known limits (tracked, not forgotten)

- The login rate limiter is in-process. It is correct for one replica; milestone 2 moves it to Redis.
- Client IP for rate limiting uses the socket peer. Behind a proxy, configure trusted proxy headers
  deliberately; never trust `X-Forwarded-For` blindly.
- Signup reveals whether an email exists (409). Accepted tradeoff, mitigated by rate limiting.
