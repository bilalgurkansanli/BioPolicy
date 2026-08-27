"""Sweeps that ride on traffic rather than a clock.

The scheduled version of this was a measured 684 GB-Hrs against a 360 GB-Hrs
ceiling, because on Fluid compute the expensive part of a cron job is waking the
container, not the work. `api/maintenance.py` moves the trigger onto requests
that have already paid for the container.

What these tests protect is the part that is easy to get wrong and invisible
when it is: this runs *after* the response, so a failure here must never reach a
user, and it must never be able to trigger itself.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

import pytest

from api.maintenance import _GATE_KEY, MAINTENANCE_INTERVAL, _sweep, schedule_if_due


@dataclass
class _Report:
    purged: int = 1
    orphans_deleted: int = 0


class _Pool:
    def __init__(self, due: Any) -> None:
        self._due = due
        self.calls: list[tuple[str, Any]] = []

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.calls.append((sql, args))
        if isinstance(self._due, Exception):
            raise self._due
        return self._due


class _Retention:
    def __init__(self) -> None:
        self.ran = 0

    async def purge_expired(self) -> _Report:
        self.ran += 1
        return _Report()


class _Worker:
    def __init__(self) -> None:
        self.ran = 0

    async def drain(self) -> int:
        self.ran += 1
        return 0


class _State:
    def __init__(self, due: Any = True) -> None:
        self.pool = _Pool(due)
        self.retention = _Retention()
        self.worker = _Worker()


@pytest.mark.asyncio
async def test_sweeps_when_the_gate_says_it_is_due() -> None:
    state = _State(due=True)
    await _sweep(cast(Any, state))
    assert state.retention.ran == 1
    assert state.worker.ran == 1


@pytest.mark.asyncio
async def test_gate_is_asked_in_postgres_not_in_this_process() -> None:
    """Several instances can be awake at once; the interval has to be shared."""
    state = _State(due=True)
    await _sweep(cast(Any, state))
    sql, args = state.pool.calls[0]
    assert "due_for_dispatch" in sql
    assert args == (_GATE_KEY, MAINTENANCE_INTERVAL)
    assert MAINTENANCE_INTERVAL == timedelta(hours=1)


@pytest.mark.asyncio
async def test_does_nothing_when_not_due() -> None:
    state = _State(due=False)
    await _sweep(cast(Any, state))
    assert state.retention.ran == 0
    assert state.worker.ran == 0


@pytest.mark.asyncio
async def test_a_broken_gate_is_not_a_failed_request() -> None:
    """This runs after the response. There is no one left to tell."""
    state = _State(due=RuntimeError("no database"))
    await _sweep(cast(Any, state))
    assert state.retention.ran == 0


@pytest.mark.asyncio
async def test_a_failing_sweep_is_swallowed() -> None:
    state = _State(due=True)

    async def explode() -> _Report:
        raise RuntimeError("storage is down")

    state.retention.purge_expired = explode  # type: ignore[method-assign]
    await _sweep(cast(Any, state))  # must not raise


def test_no_state_is_not_an_error() -> None:
    """`AppState` is None when the database was unreachable at boot."""
    schedule_if_due(None, path="/api/documents")


@pytest.mark.asyncio
async def test_internal_endpoints_do_not_trigger_a_sweep() -> None:
    """A sweep that schedules a sweep is a loop."""
    state = _State(due=True)
    schedule_if_due(cast(Any, state), path="/api/internal/purge")
    await asyncio.sleep(0)
    assert state.retention.ran == 0


@pytest.mark.asyncio
async def test_scheduling_returns_before_the_work_finishes() -> None:
    """Nothing here may be on the path a user waits for."""
    state = _State(due=True)
    schedule_if_due(cast(Any, state), path="/api/documents")
    assert state.retention.ran == 0  # not yet — it was only scheduled
    for _ in range(4):
        await asyncio.sleep(0)
    assert state.retention.ran == 1
