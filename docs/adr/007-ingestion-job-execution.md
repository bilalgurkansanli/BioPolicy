# ADR 007 — The documents table is the queue; pg_cron is the watchdog

- **Status:** accepted
- **Date:** 2026-08-04
- **Phase:** 1

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
- A `pg_cron` job runs every minute and calls `POST /api/internal/process-queue`
  with `PURGE_JOB_SECRET`. That endpoint claims work with
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

**Cost:** worst-case recovery latency is the cron interval plus the stale
threshold, so a document orphaned by an instance kill can sit for a couple of
minutes before another worker picks it up. Acceptable — that is the *failure*
path, and the happy path starts immediately. Polling also means a small constant
trickle of no-op requests when the system is idle.

The `attempts` ceiling means a genuinely malformed PDF fails after N tries
rather than immediately, spending a little money to find that out.

**Revisit if:** ingestion volume ever makes per-minute polling the wrong shape,
or if the platform gains a first-class durable background primitive.

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
