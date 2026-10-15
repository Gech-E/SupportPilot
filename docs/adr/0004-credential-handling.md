# ADR 0004: Credential handling

Status: accepted (milestone 1)

## Decision
- Argon2id with library defaults and a random salt per hash; hashing runs in a worker thread so it
  never blocks the event loop.
- Password length 12 to 128: length matters more than composition rules (NIST SP 800-63B), and the
  cap bounds the CPU an attacker can force.
- Login failures are uniform (same status, code and message). A hash is verified against a dummy
  value when the account does not exist, to keep timing similar.
- Brute-force protection: sliding-window limits per client IP and email, and per client IP overall;
  `429` with `Retry-After`.
- Emails are normalised to lowercase in the schema and enforced by a database `CHECK`.

## Known limits
Signup still reveals an existing email (`409`); this is a usability tradeoff mitigated by rate
limiting. The limiter is in-process until milestone 2 (Redis). Behind a reverse proxy the client IP
must come from trusted proxy configuration, never from a blindly trusted `X-Forwarded-For`.
