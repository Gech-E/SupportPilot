# ADR 0003: Modular monolith with one-way layering

Status: accepted (milestone 1)

## Decision
One deployable API with clear module boundaries: `routers → services → models`, and everything may
use `core`. Routers handle HTTP only; services hold business rules and raise domain errors; services
never import FastAPI. Workers (milestone 2) will reuse the same services.

## Why
One engineer can run, debug and trace the whole system. Boundaries are enforced by convention and
review (`CLAUDE.md`) now, and could become service boundaries later if a real scaling need appears.

## Consequences
Domain errors (`AppError` subclasses) are translated to one HTTP error shape in a single place, and
services are testable without HTTP.
