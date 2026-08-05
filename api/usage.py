"""Recording what every provider call cost.

`usage_events` is written after the fact, which means it is *accounting*, not a
gate. It is what the budget breaker sums and what makes "this question cost
$0.0067" a measurement rather than an estimate.

Two honest limitations, both stated in migration 0004 and repeated here because
this is where the number is produced:

* **Unpriced models contribute zero.** Google's prices were never verified for
  this project (`api/pricing.py` raises rather than guessing), so their tokens
  are recorded and their cost is not. The breaker therefore undercounts.
* **The provider console spend limit is the outer guard.** Application
  accounting can be wrong in ways application accounting cannot detect.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import asyncpg

from api.generation.llm import UsageRecord
from api.logging_config import get_logger
from api.pricing import UnpricedModelError, estimate_cost

log = get_logger(__name__)


def price(records: Sequence[UsageRecord]) -> float:
    """Total priced cost, in USD. Unpriced models count as zero, loudly."""
    total = 0.0
    for record in records:
        try:
            total += estimate_cost(
                record.model,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
            )
        except UnpricedModelError:
            log.debug("usage_unpriced", model=record.model, operation=record.operation)
    return total


class UsageRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(self, *, user_id: UUID | None, records: Sequence[UsageRecord]) -> float:
        """Write one row per provider call. Returns the priced total.

        Never raises. A failure to write the ledger must not fail a request the
        user already paid for — the answer is produced, the money is spent, and
        losing the row is strictly better than losing both.
        """
        if not records:
            return 0.0

        rows = []
        total = 0.0
        for record in records:
            try:
                cost = estimate_cost(
                    record.model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                )
            except UnpricedModelError:
                cost = 0.0
            total += cost
            rows.append(
                (
                    user_id,
                    record.operation,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    cost,
                )
            )

        try:
            await self._pool.executemany(
                """
                insert into usage_events (
                    user_id, operation, model, input_tokens, output_tokens, cost_usd
                ) values ($1, $2, $3, $4, $5, $6)
                """,
                rows,
            )
        except Exception as exc:  # the ledger is not worth failing a request over
            log.error("usage_not_recorded", error=str(exc), calls=len(rows))

        return total

    async def total_spend_usd(self) -> float:
        row = await self._pool.fetchrow(
            "select coalesce(sum(cost_usd), 0) as total from usage_events"
        )
        return float(row["total"]) if row else 0.0

    async def questions_today(self, user_id: UUID) -> int:
        """Answers billed to this user since midnight UTC.

        Counts `answer` calls rather than rows, because a single question also
        produces embedding, rewrite and verification events.
        """
        row = await self._pool.fetchrow(
            """
            select count(*) as n from usage_events
             where user_id = $1
               and operation = 'answer'
               and created_at >= date_trunc('day', now() at time zone 'utc')
            """,
            user_id,
        )
        return int(row["n"]) if row else 0
