"""The global budget breaker.

One number decides whether the demo answers anyone: the sum of `cost_usd` over
`usage_events`, against `GLOBAL_BUDGET_USD`.

## Why it is cached, and why the cache is also updated in-process

Summing the ledger on every request puts an aggregate query in front of every
question. Caching it for a few seconds fixes that and introduces a window in
which concurrent requests all see a stale, cheaper total — the classic way a
budget guard is quietly bypassed under exactly the load it exists for.

So the cache is refreshed on a timer *and* incremented locally the moment a
request finishes spending. Between refreshes the figure is therefore too high
rather than too low, which is the direction a spending limit should err in.

## What it does not protect against

A cost this codebase cannot price (see `api/usage.py`) is invisible here.
Provider-side spend limits remain the outer guard and are not optional because
this exists.
"""

from __future__ import annotations

import asyncio
import time

from api.logging_config import get_logger
from api.safety.limits import BudgetExhaustedError
from api.usage import UsageRepository

log = get_logger(__name__)

REFRESH_SECONDS = 30.0


class BudgetBreaker:
    def __init__(
        self,
        usage: UsageRepository,
        *,
        limit_usd: float,
        refresh_seconds: float = REFRESH_SECONDS,
    ) -> None:
        self._usage = usage
        self._limit = limit_usd
        self._refresh_seconds = refresh_seconds
        self._spent = 0.0
        self._checked_at = 0.0
        self._lock = asyncio.Lock()
        self._tripped = False

    @property
    def limit_usd(self) -> float:
        return self._limit

    async def spent_usd(self) -> float:
        await self._refresh_if_stale()
        return self._spent

    async def ensure_capacity(self) -> None:
        """Raise `BudgetExhaustedError` if the demo has spent its allowance."""
        await self._refresh_if_stale()
        if self._spent < self._limit:
            return

        if not self._tripped:
            # Logged once per process on the transition, not once per rejected
            # request: the interesting event is the breaker opening.
            log.error("budget_exhausted", spent_usd=round(self._spent, 4), limit_usd=self._limit)
            self._tripped = True

        raise BudgetExhaustedError(
            "This demo has reached its spending limit for now, so it is not "
            "answering new questions. Nothing was charged to you."
        )

    def note_spend(self, cost_usd: float) -> None:
        """Add spend that just happened, before the ledger is re-read.

        Called after every billable request. Cheap, synchronous and deliberately
        not awaited by the caller's critical path.
        """
        if cost_usd > 0:
            self._spent += cost_usd

    async def _refresh_if_stale(self) -> None:
        now = time.monotonic()
        if now - self._checked_at < self._refresh_seconds:
            return
        async with self._lock:
            # Re-checked inside the lock: several requests can arrive at the
            # same expiry and only one of them needs to run the aggregate.
            if time.monotonic() - self._checked_at < self._refresh_seconds:
                return
            try:
                self._spent = await self._usage.total_spend_usd()
            except Exception as exc:  # a ledger read failure must not open the gate
                log.error("budget_read_failed", error=str(exc))
                # Leave the previous figure in place. It only ever grows, so the
                # stale value is the conservative one.
            self._checked_at = time.monotonic()
            if self._tripped and self._spent < self._limit:
                # The limit was raised, or the ledger was cleared.
                log.info("budget_breaker_reset", spent_usd=round(self._spent, 4))
                self._tripped = False
