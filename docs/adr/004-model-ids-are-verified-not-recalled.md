# ADR 004 — Model IDs are verified against a live list, never recalled from memory

- **Status:** accepted (two IDs pending verification — see below)
- **Date:** 2026-08-03
- **Phase:** 0

## Context

This project's entire thesis is that a system should refuse to state things it
cannot ground. It would be an embarrassing inconsistency for the codebase to
ship a hardcoded model identifier that someone half-remembered, and model IDs
are unusually easy to get wrong: they are long, they are versioned by date,
they change on a cadence measured in months, and a wrong one fails at runtime
with an unhelpful 404 rather than at import.

The spec's rule 6 says so explicitly: don't fabricate model IDs, ask.

## Decision

Model identifiers live in configuration, never in code.

- `ANTHROPIC_MODEL` defaults to `claude-haiku-4-5-20251001`. This one is
  **verified**: it is the identifier for Claude Haiku 4.5 and is confirmed
  against the running environment's own model list.
- `GEMINI_FALLBACK_MODEL` and `GEMINI_OCR_MODEL` default to the **empty
  string**, not to a guess. Empty means "this capability is unavailable" —
  `/api/health` reports it as `unconfigured`, provider failover skips the
  fallback, and the OCR path returns a clean error instead of a 404 from
  Google.

They are filled in at Phase 1 by enumerating the live model list with the
project's own API key, and the verified values are recorded in
`docs/RUNBOOK.md` alongside the date they were checked.

## Consequences

**Bought:** no fabricated identifier can reach production. A capability that
isn't configured degrades visibly and specifically instead of failing as a
generic provider error. Rotating to a newer model is an environment variable,
not a deploy.

**Cost:** the service can start in a state where OCR and LLM failover don't
work, and it is on the operator to notice. This is mitigated by `/api/health`
naming each unconfigured capability, and by the startup log line listing them.

Note the asymmetry with ADR 001: the Supabase and Anthropic credentials are
*required* in deployed environments, while these two model IDs are not. That is
deliberate — OCR and failover are degradable features, whereas a missing
database is not a degraded service, it is a broken one.

## Alternatives considered

**Hardcode plausible IDs and fix them when they 404.** This is the normal thing
to do and it is precisely the behaviour the product exists to argue against.

**Discover the model at startup by querying the provider's list endpoint and
picking the newest match.** Tempting, and genuinely self-maintaining. Rejected:
it makes the model in use non-deterministic across deploys, which silently
invalidates the evaluation report — every number in `eval/report.md` is only
meaningful next to a fixed model version. It also adds a network call to cold
start.
