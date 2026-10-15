# SupportPilot

A multi-tenant SaaS that gives small businesses an AI support agent for their website. The agent
answers **only from the business's own documents, with citations**, and hands the conversation to a
human when it is not confident.

> **Status: milestone 1 of 6 (foundation).** Authentication, workspaces, tenant isolation enforced by
> PostgreSQL, CI and containers are done. Ingestion, RAG, the widget, evals and the dashboard follow
> the [roadmap](#roadmap). Nothing in this repository claims AI quality numbers yet; those will come
> from the evaluation harness, with the method published first.

## What exists today

| Area | Implemented |
| --- | --- |
| Accounts | Signup and login with Argon2id, uniform login errors, brute-force rate limiting |
| Sessions | Signed JWT in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie, plus a CSRF token bound to the session |
| Workspaces | Create, read, update (owner only), list members, roles `owner` and `agent` |
| Tenant isolation | PostgreSQL row-level security (forced), restricted API database role, least-privilege grants |
| Platform | Typed settings that fail fast, structured JSON logs with request ids, one error shape, security headers, health and readiness probes |
| Delivery | Docker (non-root, read-only filesystem), Compose, GitHub Actions (lint, types, tests, dependency audit, secret scan), Dependabot |
| Developer workflow | `CLAUDE.md` files and project skills for Claude Code (see below) |

## Architecture in one picture

```
Browser / widget ──HTTPS──▶ FastAPI (stateless) ──SQL as role supportpilot_app──▶ PostgreSQL
                                   │                                              ▲
                                   │  per request, in one transaction:            │ row-level security
                                   │  1. verify session cookie → set app.user_id  │ decides which rows
                                   │  2. verify membership    → set app.workspace_id  this role can see
                                   ▼
                    routers → services → models   (one-way dependencies)
```

The key design choice is that **the database enforces tenant isolation**, not just the application.
If a developer forgets a `WHERE workspace_id = ...`, PostgreSQL still returns nothing from another
tenant. See [ADR 0001](docs/adr/0001-tenant-isolation-with-row-level-security.md).

## Quick start

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Python 3.12+.

```bash
cp .env.example .env        # then replace every CHANGE_ME value (see the comments in the file)
make lock                   # once: writes services/api/uv.lock, which the Docker build installs from
make up                     # Postgres + migrations + API on http://127.0.0.1:8000
```

Try it (local development uses `COOKIE_SECURE=false` so cookies work over plain HTTP):

```bash
# 1. sign up; the session and CSRF cookies are saved in ./jar
curl -s -c jar -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"a long passphrase"}' \
  http://127.0.0.1:8000/api/v1/auth/signup

# 2. state-changing requests must echo the CSRF cookie in a header
CSRF=$(awk '$6=="sp_csrf"{print $7}' jar)
curl -s -b jar -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"name":"Acme Bakery"}' http://127.0.0.1:8000/api/v1/workspaces

# 3. who am I, and which workspaces do I belong to?
curl -s -b jar http://127.0.0.1:8000/api/v1/me
```

Interactive API docs are served at `/docs` outside staging and production.

## Development

```bash
make setup       # virtualenv + dependencies
make lint        # ruff (including security rules) and format check
make typecheck   # mypy --strict
make test        # unit + integration tests
make audit       # known-vulnerability scan of dependencies
make format      # auto-fix formatting
```

Integration tests need a PostgreSQL server (any 14+; a superuser connection is used to create a
scratch database and the restricted role):

```bash
export TEST_ADMIN_DSN=postgresql://postgres:postgres@localhost:5432/postgres
export TEST_APP_PASSWORD=any_throwaway_value
make test
```

The tests run the real Alembic migrations and connect as the restricted `supportpilot_app` role, so
row-level security is exercised exactly as in production. `tests/integration/test_rls.py` talks to
the database directly, with no API in between, to prove isolation holds even if application code
forgets a filter.

## Security model (summary)

Full detail and the threat model: [docs/security.md](docs/security.md).

- Secrets only from the environment; production refuses placeholder or short secrets.
- Passwords: Argon2id, 12-character minimum, never logged or returned.
- Sessions in `HttpOnly` cookies (not readable by scripts); CSRF token required on every
  state-changing request and bound to the session.
- Authorization on every route through dependencies; another tenant's resources return `404`.
- Row-level security on every tenant table, forced, with a CI test that fails if a table lacks it.
- The API role cannot delete rows, cannot bypass RLS, and cannot read password hashes directly.
- Errors never leak internals or echo submitted values; every response carries a request id.

## Working with Claude Code

This repository is set up so an AI coding agent follows the same standards as a human contributor.

| File | Purpose |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Project rules, commands, clean-code standards, definition of done |
| [`services/api/CLAUDE.md`](services/api/CLAUDE.md) | Backend layering, request flow, conventions, known limits |
| `.claude/skills/add-endpoint` | Step-by-step procedure for a new route |
| `.claude/skills/add-migration` | Migrations and the mandatory RLS checklist for tenant tables |
| `.claude/skills/security-review` | Checklist for reviewing a diff |
| `.claude/skills/rag-change-with-evals` | Measure-before-and-after procedure for any retrieval or prompt change |
| `.claude/settings.json` | Pre-approved safe commands; denies reading `.env` and key files |

## Roadmap

| Milestone | Scope | Gate |
| --- | --- | --- |
| 1. Foundation (done) | Auth, tenancy, RLS, CI, containers | Isolation tests pass in CI |
| 2. RAG core | Ingestion jobs, chunking, embeddings (pgvector), cited answers | Cited answers on sample documents |
| 3. Widget | Embeddable iframe widget, streaming, stored conversations | End-to-end chat demo |
| 4. Retrieval and handoff | Hybrid search, reranking, confidence gate, agent inbox | A human reply reaches the customer |
| 5. Evaluation | Golden dataset, eval runner, guardrails, tracing and cost | Baseline and ablation numbers recorded in [`docs/eval-log.md`](docs/eval-log.md) |
| 6. Polish | Dashboard, demo video, write-up | Launch checklist complete |

## Known limitations of milestone 1

These are deliberate and tracked, not forgotten.

- Rate limiting is in-process (correct for one replica). Redis-backed limiting arrives with milestone 2.
- Sessions are stateless JWTs: logging out clears the cookie, but a stolen token stays valid until it
  expires (60 minutes by default). Server-side revocation is planned.
- Signup reveals whether an email is registered (`409`). Rate limiting reduces enumeration.
- Inviting members by email, and deleting workspaces, are not implemented yet; the database denies
  those operations until reviewed policies exist.
