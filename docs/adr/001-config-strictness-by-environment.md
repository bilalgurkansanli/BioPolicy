# ADR 001 — Configuration is strict when deployed, permissive in development

- **Status:** accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

The spec calls for "env config that fails loudly on missing keys". The obvious
reading is: make every credential a required field, so the process refuses to
start without it.

That reading has a cost I ran into within the first hour. This project has seven
required credentials across three providers. If all of them are mandatory
unconditionally, then nothing runs on a laptop until every account exists —
not the test suite, not `ruff`, not the health endpoint, not CI. Phase 0 would
be blocked on Phase 5's accounts.

The failure mode we are actually trying to prevent is narrower and worse than
"a developer forgot a key": it is **a deployment that boots successfully with a
credential missing** and then fails hours later, in front of a user, as a 500
that looks like a bug in the retrieval code.

## Decision

`Settings` treats credentials as optional fields, and a `model_validator`
rejects the whole configuration if `APP_ENV` is `preview` or `production` and
any of them is empty. The error names **every** missing variable at once, not
the first one.

In `development`, missing credentials are reported — at boot as a warning, and
by `/api/health` as `"unconfigured"` per provider — but are not fatal.

## Consequences

**Bought:** the scaffold, the unit tests and CI all run with no accounts
attached, which is what let Phase 0 finish before Supabase existed. A deployed
environment cannot boot half-configured. An operator fixing a bad deploy sees
the complete list of what's missing on the first attempt instead of discovering
them one restart at a time.

**Cost:** `development` can reach a code path whose provider is unconfigured. The
mitigation is that such endpoints must return a clean `503` naming the missing
capability — that is a rule the endpoint authors have to follow, and a rule is
weaker than a type. If this leaks confusing local failures, the fix is a
dependency that guards each router at request time, not making the fields
required.

**Revisit if:** we add a fourth environment, or if `development` starts being
used for anything a user can reach.

## Alternatives considered

**All fields required, always.** Rejected: blocks all local work on account
creation, and encourages the workaround of committing a `.env` full of dummy
values, which is strictly worse — it defeats the check everywhere including
production.

**Separate `Settings` subclasses per environment.** More typed, and genuinely
appealing. Rejected as over-engineering for seven fields; it doubles the surface
that has to stay in sync with `.env.example` for no behaviour we don't get from
one validator.

**Fail at first use rather than at boot.** This is the default behaviour of most
SDKs and it is exactly the failure mode described in Context.
