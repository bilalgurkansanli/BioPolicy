"""Maintenance that rides on traffic instead of a clock.

## Why there is no scheduled job any more

Migration 0007 had Postgres call this API on a timer. That is the ordinary
shape, and on per-invocation serverless it is nearly free. On Vercel Fluid
compute it is not: a container is billed for its whole lifetime, and it only
scales down after five minutes without traffic, so every scheduled call buys a
five-minute minimum of provisioned memory whether or not there was any work.

The measured cost of a one-minute schedule was 684 GB-Hrs against a 360 GB-Hrs
ceiling. Migration 0015 cut it to one dispatch a week; 0016 removes it entirely
in favour of this module.

The observation that makes this work: **a request from a real user has already
paid for the container.** It is awake, the five-minute tail is already running,
and the marginal cost of also draining the queue and purging expired documents
during that window is close to zero. Scheduling is what costs money here, not
the work itself.

## What this is not

It is not a replacement for durability. `purge_expired_rows()` still runs hourly
inside Postgres — free, no HTTP, no container — and it is what actually holds
the 24-hour promise for the database. This module deletes the storage objects
that function cannot reach, and it drains any document the in-process fast path
dropped.

The honest limitation is that a site with no visitors does no cleanup. Rows
still expire on time, so nothing stays readable; the files wait for the next
visitor. For a site whose whole purpose is to be visited, the arrival of a
visitor is a better trigger than a clock — the work exists because people upload
things, so it appears exactly when they do.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from api.logging_config import get_logger

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime
    from api.deps import AppState

log = get_logger(__name__)

# How stale the last sweep must be before a request triggers another. An hour
# matches `purge_expired_rows()`, so the two halves of retention run at roughly
# the same cadence on a site that has visitors.
MAINTENANCE_INTERVAL = timedelta(hours=1)

# The gate lives in Postgres, not in this process. Several instances can be
# awake at once and each one sees its own memory; `due_for_dispatch` is a single
# row updated inside one statement, so exactly one of them wins the hour.
_GATE_KEY = "opportunistic_maintenance"

# `asyncio.create_task` only holds a weak reference. Without this the task can be
# garbage collected mid-flight, which produces no error and no work — the worst
# combination to debug.
_running: set[asyncio.Task[None]] = set()


async def _sweep(state: AppState) -> None:
    try:
        due = await state.pool.fetchval(
            "select due_for_dispatch($1, $2)", _GATE_KEY, MAINTENANCE_INTERVAL
        )
    except Exception as exc:  # pragma: no cover - exercised against Postgres
        # A maintenance sweep is never worth failing a user's request over, and
        # this runs after the response has already gone out.
        log.warning("maintenance_gate_failed", error=str(exc))
        return

    if not due:
        return

    try:
        report = await state.retention.purge_expired()
        processed = await state.worker.drain()
        log.info(
            "maintenance_swept",
            purged=report.purged,
            orphans_deleted=report.orphans_deleted,
            processed=processed,
        )
    except Exception as exc:
        log.error("maintenance_failed", error=str(exc))


def schedule_if_due(state: Any | None, *, path: str) -> None:
    """Fire a sweep in the background if one is due. Never raises, never waits.

    Called from middleware after the response, so nothing here is on the path a
    user waits for. The `path` guard keeps the internal endpoints out: they do
    this same work explicitly, and a sweep that schedules a sweep is a loop.
    """
    if state is None or path.startswith("/api/internal/"):
        return

    task = asyncio.create_task(_sweep(state))
    _running.add(task)
    task.add_done_callback(_running.discard)
