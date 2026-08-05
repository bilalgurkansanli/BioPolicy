"""What the demo has spent, in public.

A project whose stated ethic is publishing its own numbers should not stop at
the flattering ones. This endpoint reads `usage_events` and says what the demo
has actually cost — total, per question, and how much of the budget is left.

No authentication. It is aggregate, it contains nobody's data, and putting it
behind a sign-in would make it a number the project claims rather than one a
reader can check.

## The figure is Anthropic-only, and says so

`api/pricing.py` refuses to invent a price it has not verified, so Google's
embedding and rewriting calls are recorded with their tokens and a cost of zero
(`api/usage.py`). The real bill is therefore higher than this number. The
response carries `priced_share` so a reader can see how much of the traffic the
figure actually covers rather than having to trust that it covers all of it.
"""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import Config, State

router = APIRouter(prefix="/stats", tags=["stats"])

# The figure is an aggregate over a table that only grows, and the endpoint is
# public and unauthenticated by design. Without a cache, anyone could turn a
# published number into a way to make the database do arithmetic on demand.
#
# Sixty seconds is far below the rate at which the number changes in any way a
# reader would notice, and far above the rate at which a scraper could hurt
# anything.
CACHE_SECONDS = 60.0
_cached: tuple[float, Spend] | None = None


class Spend(BaseModel):
    total_usd: float
    budget_usd: float
    questions: int
    per_question_usd: float | None
    """`null` before the first question, rather than a division by zero."""

    provider_calls: int
    priced_calls: int
    priced_share: float
    """Fraction of provider calls this figure covers. Below 1.0 by design."""

    first_call_at: str | None


@router.get("", response_model=Spend, summary="What this demo has cost")
async def spend(state: State, settings: Config) -> Spend:
    global _cached
    if _cached is not None and time.monotonic() - _cached[0] < CACHE_SECONDS:
        return _cached[1]

    row = await state.pool.fetchrow(
        """
        select coalesce(sum(cost_usd), 0)                       as total,
               count(*)                                          as calls,
               count(*) filter (where cost_usd > 0)              as priced,
               count(*) filter (where operation = 'answer')      as questions,
               min(created_at)                                   as first_call
          from usage_events
        """
    )
    total = float(row["total"]) if row else 0.0
    calls = int(row["calls"]) if row else 0
    priced = int(row["priced"]) if row else 0
    questions = int(row["questions"]) if row else 0

    result = Spend(
        total_usd=round(total, 4),
        budget_usd=settings.global_budget_usd,
        questions=questions,
        per_question_usd=round(total / questions, 6) if questions else None,
        provider_calls=calls,
        priced_calls=priced,
        priced_share=round(priced / calls, 3) if calls else 0.0,
        first_call_at=row["first_call"].isoformat() if row and row["first_call"] else None,
    )
    _cached = (time.monotonic(), result)
    return result
