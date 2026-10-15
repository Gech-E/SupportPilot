# Security notes

Scope: milestone 1 (accounts, sessions, workspaces, tenant isolation). LLM-specific threats
(prompt injection, output exfiltration, cost abuse) are designed in the technical documentation and
will be implemented and tested from milestone 2.

## Threat model

| Threat | Mitigation | Verified by |
| --- | --- | --- |
| Cross-tenant data access through a code bug | Forced row-level security; restricted database role | `tests/integration/test_rls.py` (direct SQL as the app role) |
| Mass listing of accounts or password hashes | RLS on `users`; hashes readable only through `auth_find_user` for one exact email | RLS tests: no-context read, wildcard lookup |
| Privilege escalation inside a workspace | Owner checks in routes **and** in database policies | API tests (agent gets 403) and RLS tests |
| Claiming ownership of someone else's workspace | Bootstrap exception only for a workspace with no members, and only for oneself | RLS tests |
| Session forgery | HS256 with pinned algorithm, required claims, issuer check; secret length enforced at startup | `tests/unit/test_tokens.py` (alg `none`, tampering, expiry, wrong issuer) |
| CSRF | Token bound to the session, constant-time compare, `SameSite=Lax` | Unit and API tests |
| XSS stealing the session | `HttpOnly` cookie; API sends `default-src 'none'` CSP | Cookie flag test; header tests |
| Credential stuffing and brute force | Argon2id; rate limits per IP and per IP plus email | Rate-limit unit and API tests |
| Account enumeration through login | Uniform errors and similar timing | API test comparing responses |
| Information leakage in errors | One error shape; no internals; validation errors never echo values | API tests |
| Misconfiguration in production | Startup refuses short or placeholder secrets and insecure cookies; docs disabled | `tests/unit/test_config.py` |
| Compromised dependency | Dependabot, `pip-audit` in CI, secret scanning in CI | CI pipeline |
| Container breakout or tampering | Non-root user, read-only filesystem, all capabilities dropped, no-new-privileges | `docker-compose.yml` |

## Operational notes

- Run migrations as the owner role and the API as `supportpilot_app`. In production use a managed
  PostgreSQL where the owner is **not** a superuser; superusers bypass row-level security.
- Rotate `SESSION_SECRET` to invalidate every session at once.
- Behind a reverse proxy, configure trusted proxy headers deliberately so rate limiting sees the real
  client address, and terminate TLS there (HSTS is sent when `APP_ENV` is staging or production).

## Reporting a vulnerability

Open a private security advisory on the repository rather than a public issue.

## Known limitations

- Stateless sessions cannot be revoked before expiry (60 minutes by default).
- The login rate limiter is per process; use the Redis-backed limiter before running replicas.
- No email verification or password reset yet.
- No audit log yet; planned with the inbox in milestone 4.
