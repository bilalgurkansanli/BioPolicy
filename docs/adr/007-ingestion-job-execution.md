# ADR 007 — The documents table is the queue; pg_cron is the watchdog

- **Status:** accepted, amended 2026-08-27
- **Date:** 2026-08-04
- **Phase:** 1

> **Amended 2026-08-27.** The decision holds; the trigger does not. The
> watchdog polled every minute, which was free on per-invocation serverless and
> is not free on Vercel Fluid compute, where an instance is billed for its whole
> lifetime and only scales down after five idle minutes. A minutely poll means
> it never scales down: 684 GB-Hrs against a 360 GB-Hrs ceiling, and the project
> was paused.
>
> Migration 0015 cut both HTTP jobs to one dispatch a week, and 0016 removed
> them. `pg_cron` is no longer the watchdog — `api/maintenance.py` is, running
> the same sweeps on request traffic that has already paid for the container.
> The *Consequences* below are rewritten to match; the *Decision* — that the
> `documents` table is the queue — is unchanged.

## Context

Constraint C2 says ingestion must be asynchronous: `POST /documents` returns
`202` and a multi-minute pipeline runs out of band. The spec's repository layout
implies `ingest/pipeline.py` is simply called in the background.

On a scale-to-zero container that is not safe. Once the response is written, the
platform is free to freeze or reclaim the instance. An in-process background task
has no durable record that it was ever started, so when it dies the document sits
in `parsing` forever and nothing retries it. The user watches a progress
indicator that will never advance.

This is the difference between "asynchronous" and "durable", and only the second
one is actually a job system.

## Decision

The `documents` table **is** the queue. No external queue service.

- `POST /documents` inserts the row with `status='queued'` and returns `202`.
  This is the durable record; everything after it is recoverable.
- It then fires a **best-effort** in-process task to start work immediately, so
  the common case has no added latency.
- `POST /api/internal/process-queue`, authorised with `PURGE_JOB_SECRET`, is
  the watchdog. A `pg_cron` job called it every minute until migration 0015 cut
  it to weekly and 0016 removed the schedule entirely; `api/maintenance.py` now
  runs the same sweep on request traffic — see *Consequences*. The endpoint
  remains, and claims work with
  `SELECT … FOR UPDATE SKIP LOCKED`, which makes concurrent workers safe without
  a lock service.
- A row is claimable if it is `queued`, **or** if it is in a working state with
  `claimed_at` older than a stale threshold — that second clause is what
  recovers documents stranded by a killed instance.
- `attempts` is incremented on claim. Past a retry ceiling the row goes to
  `failed` with a user-safe message, so a document that reliably crashes the
  parser cannot become an infinite billing loop.

Pipeline stages are **idempotent and resumable**: a retry deletes any chunks
already written for that document before re-chunking, so a partial run cannot
produce duplicates.

## Consequences

**Bought:** durability without a fourth vendor, using infrastructure the project
already depends on. Crash recovery falls out of the stale-claim rule rather than
needing separate machinery. `SKIP LOCKED` means the immediate task and the cron
sweep can race harmlessly — whoever claims the row first wins, the other gets
nothing.

**Cost:** worst-case recovery latency is no longer a number this ADR controls.
It was the cron interval plus the stale threshold — a couple of minutes. It is
now *whenever somebody next uses the site*, plus at most an hour of the gate in
`api/maintenance.py`. On a site with visitors that is often better than a
one-minute poll, because the sweep fires exactly when documents are being
created. On a site with none it is unbounded.

So the honest description of the watchdog today is *eventual cleanup*, not
*recovery*, and what carries the happy path is the in-process fast path — which
is exactly the thing this ADR called an optimisation and never the durable
mechanism. That inversion is the real cost and it is worth naming: the durable
mechanism still exists and still works, but nothing guarantees when it runs.

What is *not* traded away is the deletion promise for the database.
`purge_expired_rows()` still runs hourly inside Postgres, costs nothing on the
meter that caused this, and needs no visitor. Rows expire on a clock; only the
storage objects wait for traffic.

The `attempts` ceiling means a genuinely malformed PDF fails after N tries
rather than immediately, spending a little money to find that out.

**Revisit if:** ingestion volume grows enough that a week of stranded documents
is visible to real users, if the API moves to a host that does not bill for idle
time — which would make the original one-minute interval free again — or if the
platform gains a first-class durable background primitive.

## Alternatives considered

**`BackgroundTasks` alone.** What the spec's layout implies. Rejected: no
durability, no retry, no visibility. Its failure mode is a document permanently
stuck in `parsing`, which is invisible to the operator and looks to the user
like the product is broken. Kept only as the *fast path*, with the queue as the
guarantee.

**A hosted queue (QStash, Inngest, Cloud Tasks).** The textbook answer and
genuinely better at scale — real retry semantics, dead-letter queues,
observability. Rejected for v1: a fourth vendor, another key to rotate, another
failure mode to explain, and another line item against a $30 ceiling, to solve a
problem that one table and one cron entry already solve at this size.

**Supabase Edge Functions for ingestion.** Would need the parsing stack ported
to Deno. Non-starter given the Python PDF pipeline.

**A long-running worker process on another host.** Simplest correct answer, and
it removes the problem rather than managing it. Rejected because it abandons the
one-platform property that motivated the deployment topology in ADR 006 — but
this is the fallback if the queue approach proves fragile, and it pairs with the
same fallback noted there.
