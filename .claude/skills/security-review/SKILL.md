---
name: security-review
description: Security checklist for reviewing a SupportPilot diff or finishing a feature. Covers secrets, authentication, authorization, tenant isolation, injection, LLM prompt injection, logging, and dependencies.
---

# Security review checklist

Review the diff (`git diff main...HEAD`) against each item. Report findings as
`file:line - problem - fix`. Do not mark an item done without checking the code.

## Secrets and config
- [ ] No keys, passwords, tokens, or connection strings in code, tests, docs, or examples
- [ ] New settings are validated in `app/core/config.py`; production rejects placeholder values
- [ ] `.env.example` has placeholders only

## Authentication and sessions
- [ ] Cookies are `HttpOnly`, `Secure` (production), `SameSite=Lax`, with an expiry
- [ ] Mutating cookie-authenticated routes depend on `verify_csrf`
- [ ] Login failures are uniform (same status, code, and similar timing for unknown users)
- [ ] Passwords hashed with Argon2id; never logged, returned, or stored in plain text

## Authorization and tenant isolation
- [ ] Every new route has an explicit dependency: user, member, or owner
- [ ] Workspace RLS context is set only after membership is verified
- [ ] Other tenants' resources return 404
- [ ] New tenant tables follow the `add-migration` skill (forced RLS, per-command policies, tests)
- [ ] The app role has the minimum grants; no `DELETE`/`UPDATE` unless needed

## Input and injection
- [ ] All inputs validated with bounded Pydantic fields
- [ ] No string-built SQL; no `eval`/`exec`; no shell commands built from user input
- [ ] Uploaded files: size limit, type check by content, parsed with time and memory limits
- [ ] Any server-side URL fetch blocks private, loopback, and link-local addresses, including after redirects

## LLM and retrieval (when applicable)
- [ ] Retrieved text and customer messages are wrapped as data, never concatenated into instructions
- [ ] The model has no tool with side effects beyond `handoff_to_human`
- [ ] No secrets or other tenants' data in any prompt
- [ ] Output rendering allows no images, raw HTML, or links outside the allow-list
- [ ] Red-team cases still pass in the eval suite

## Logging and errors
- [ ] No passwords, tokens, message bodies, or full emails in logs
- [ ] Errors use `AppError`; no stack traces or SQL text reach the client
- [ ] Validation errors do not echo submitted values

## Dependencies
- [ ] New packages are necessary, maintained, and pinned by lower bound
- [ ] `make audit` is clean or each finding has a documented exception

## Output
End with: **Blocking issues**, **Should fix**, **Notes**. If there are no blocking issues, say so
explicitly.
