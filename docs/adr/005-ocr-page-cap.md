# ADR 005 — Vision OCR is capped at 30 pages, enforced before the job starts

- **Status:** accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

The global budget is a $30 hard ceiling for the entire public demo — every
upload, every question, from every visitor, for as long as it is online.

Within that budget, costs are not remotely uniform. Text embedding is cheap
enough to be a rounding error. Generation is small and bounded by output token
caps. Vision OCR is different in kind: a rendered page at 200 DPI is a large
image, images are billed by area, and the cost scales linearly with page count
with no natural ceiling. A single 200-page scanned policy is not a marginal
cost against a $30 budget — it is a meaningful fraction of it, spent by one
visitor, in one upload, before anyone asks a question.

The circuit breaker in Section 10 does not save us here. It checks cumulative
spend and trips *after* the money is gone. For an operation this lumpy, a
post-hoc breaker is a smoke alarm in a house that has already burned down.

## Decision

`MAX_OCR_PAGE_COUNT` defaults to 30 and is enforced at **upload validation
time**, before the ingestion job is enqueued — not partway through the pipeline
after N pages have already been billed.

A document that exceeds it is rejected with a specific, user-facing message
naming the limit, rather than a generic failure. `config.py` refuses to start if
`MAX_OCR_PAGE_COUNT > MAX_PAGE_COUNT`, so the cheap-path limit can never be the
one that binds first, and there is a unit test for it.

Native-text documents keep the much higher `MAX_PAGE_COUNT` of 250: reading an
existing text layer costs nothing but CPU.

## Consequences

**Bought:** the single worst-case cost path in the system is bounded before any
money is spent. Worst case per scanned upload is knowable in advance rather than
discovered from a bill.

**Cost:** a legitimate visitor with a long scanned policy is turned away. That
is a real product limitation and the UI has to say so honestly — naming the page
limit, not hiding behind "something went wrong". It also means the "handles
scanned Turkish PDFs" claim in the demo carries an asterisk, and the README
should carry it too.

**Revisit if:** actual spend data from the live demo shows OCR is a small
fraction of the total, in which case raise the cap with evidence rather than
optimism.

## Alternatives considered

**Rely on the global circuit breaker alone.** Rejected: it trips after the
spend, and one document can consume a large share of the budget between two
checks.

**OCR the first 30 pages and answer from those, silently.** Rejected outright,
and it is worth saying why at length: it would produce a system that confidently
answers "that isn't covered in this document" about a clause on page 84 that it
never read. That is the exact failure this product is built to prevent, dressed
up as a feature. A refusal that is grounded in a truncated document is a lie
with a citation. Truncation is only acceptable if the truncation is disclosed on
every answer, and at that point rejecting the upload is both cheaper and more
honest.

**Charge users / require an account with a quota.** Out of scope for v1, and the
per-user daily document quota already limits the repeat case. This cap addresses
the single-upload case that quotas don't.
