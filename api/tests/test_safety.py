"""Quotas and the budget breaker.

Both exist because this demo is public and every question costs real money. The
tests worth having are about the edges: what happens *at* the limit rather than
below it, and whether spend that has happened but is not yet in the ledger still
counts.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest

from api.safety.breaker import BudgetBreaker
from api.safety.limits import BudgetExhaustedError, DailyQuotaExceededError
from api.safety.quota import QuotaGuard
from api.tests.fakes import FakePool
from api.usage import UsageRepository

USER = uuid4()


def _guard(
    *, asked: int = 0, uploaded: int = 0, questions: int = 3, documents: int = 2
) -> QuotaGuard:
    # Two fetchrow results: the first answers `questions_today`, the second the
    # upload count. Each test only exercises one of them.
    pool = FakePool(fetchrow=[{"n": asked}, {"n": uploaded}])
    usage = UsageRepository(cast(Any, pool))
    return QuotaGuard(
        cast(Any, pool),
        usage,
        daily_questions=questions,
        daily_documents=documents,
    )


# -----------------------------------------------------------------------------
# quotas
# -----------------------------------------------------------------------------


async def test_a_user_below_the_daily_limit_is_served() -> None:
    await _guard(asked=2, questions=3).ensure_can_ask(USER)


async def test_the_limit_binds_at_the_limit_not_after_it() -> None:
    """Off-by-one here means the advertised limit is silently one higher."""
    with pytest.raises(DailyQuotaExceededError):
        await _guard(asked=3, questions=3).ensure_can_ask(USER)


async def test_the_quota_message_says_when_it_resets() -> None:
    """A limit with no stated reset reads as a permanent ban."""
    with pytest.raises(DailyQuotaExceededError) as caught:
        await _guard(asked=9, questions=3).ensure_can_ask(USER)

    assert "midnight UTC" in caught.value.message
    assert caught.value.as_http().status_code == 429
    assert caught.value.retry_after_seconds is not None


async def test_uploads_have_their_own_limit() -> None:
    guard = _guard(asked=0, uploaded=2, documents=2)
    await guard.ensure_can_ask(USER)  # questions are unaffected

    with pytest.raises(DailyQuotaExceededError):
        await guard.ensure_can_upload(USER)


async def test_the_upload_count_ignores_samples() -> None:
    """Assertion about the query text, for the same reason as retention's.

    Counting samples would charge every visitor three documents before they
    uploaded anything.
    """
    pool = FakePool(fetchrow=[{"n": 0}])
    guard = QuotaGuard(
        cast(Any, pool),
        UsageRepository(cast(Any, pool)),
        daily_questions=10,
        daily_documents=10,
    )

    await guard.ensure_can_upload(USER)

    assert "not is_sample" in pool.queries[0]


# -----------------------------------------------------------------------------
# the budget breaker
# -----------------------------------------------------------------------------


def _breaker(spent: float, *, limit: float = 30.0, refresh: float = 30.0) -> BudgetBreaker:
    pool = FakePool(fetchrow=[{"total": spent}] * 10)
    return BudgetBreaker(UsageRepository(cast(Any, pool)), limit_usd=limit, refresh_seconds=refresh)


async def test_spending_below_the_budget_is_served() -> None:
    await _breaker(29.99).ensure_capacity()


async def test_reaching_the_budget_stops_everyone() -> None:
    with pytest.raises(BudgetExhaustedError):
        await _breaker(30.0).ensure_capacity()


async def test_an_exhausted_budget_is_a_503_not_a_429() -> None:
    """A 429 invites the retry loop this exists to prevent.

    "Too many requests" tells a client to back off and try again; no amount of
    retrying refills a budget, and the polite clients would hammer hardest.
    """
    with pytest.raises(BudgetExhaustedError) as caught:
        await _breaker(50.0).ensure_capacity()

    assert caught.value.as_http().status_code == 503


async def test_spend_counts_before_it_reaches_the_ledger() -> None:
    """The window this closes is the one that matters.

    Usage is written after a call completes and the total is cached for
    seconds. Without in-process accounting, every request arriving inside that
    window sees the same stale, cheaper figure — so the breaker is bypassed by
    exactly the concurrency it exists to survive.
    """
    breaker = _breaker(29.0, limit=30.0, refresh=30.0)
    await breaker.ensure_capacity()  # fine, and the total is now cached

    breaker.note_spend(1.5)

    with pytest.raises(BudgetExhaustedError):
        await breaker.ensure_capacity()


async def test_a_ledger_read_failure_does_not_open_the_gate() -> None:
    """A database hiccup must not be a licence to spend.

    The previous figure is kept, which is the conservative choice: the total
    only ever grows, so a stale reading is an underestimate of spend and never
    an underestimate of remaining budget.
    """

    class FailingPool(FakePool):
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            raise RuntimeError("connection reset")

    breaker = BudgetBreaker(
        UsageRepository(cast(Any, FailingPool())), limit_usd=30.0, refresh_seconds=0.0
    )
    breaker.note_spend(31.0)

    with pytest.raises(BudgetExhaustedError):
        await breaker.ensure_capacity()
