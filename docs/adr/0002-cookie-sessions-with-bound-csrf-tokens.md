# ADR 0002: HttpOnly cookie sessions with a session-bound CSRF token

Status: accepted (milestone 1)

## Context
The dashboard is a browser app. Session tokens kept in `localStorage` can be stolen by any script
injected into the page (XSS).

## Decision
- The session is a signed JWT (HS256, pinned algorithm, issuer and expiry required) in an
  `HttpOnly`, `Secure`, `SameSite=Lax` cookie.
- A second, script-readable cookie carries a CSRF token: an HMAC of the session token. The dashboard
  echoes it in `X-CSRF-Token`, and the server recomputes and compares it in constant time.
  Binding to the session means a planted cookie from a sibling subdomain cannot produce a valid pair.
- CORS lists exact origins; `*` is rejected at startup.

## Alternatives considered
- **Bearer token in `localStorage`.** Exposed to XSS.
- **Opaque server-side sessions (Redis).** Allows instant revocation; planned once Redis arrives in
  milestone 2.

## Consequences
- Stateless and simple to scale, at the cost of no server-side revocation until the token expires
  (60 minutes by default). This is listed under known limitations.
- Non-browser clients must send the CSRF header too; the widget uses separate short-lived visitor
  tokens (milestone 3) and does not use these cookies.
