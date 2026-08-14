"""Quotas and the budget breaker.

Both exist because this demo is public and every question costs real money. The
tests worth having are about the edges: what happens *at* the limit rather than
below it, and whether spend that has happened but is not yet in the ledger still
counts.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from api.accounts import Account
from api.safety.breaker import BudgetBreaker
from api.safety.limits import (
    AccountNotUsableError,
    BudgetExhaustedError,
    DailyQuotaExceededError,
)
from api.safety.quota import QuotaGuard
from api.tests.fakes import FakePool
from api.usage import UsageRepository

USER = uuid4()


def _account(*, usable: bool) -> Account:
    return Account(
        id=USER,
        email="tester@example.com",
        provider="google",
        email_confirmed=True,
        usable=usable,
    )


# `usable` is the repository's own conclusion from banned / deleted /
# is_anonymous — that mapping is tested in `test_accounts.py`. Here the three
# cases are the same flag, kept apart by name so a failure says which state was
# meant to be refused.
_USABLE = _account(usable=True)
_BANNED = _account(usable=False)
_DELETED = _account(usable=False)
_ANONYMOUS = _account(usable=False)


def _guard(
    *,
    asked: int = 0,
    uploaded: int = 0,
    questions: int = 3,
    documents: int = 2,
    unlimited: bool = False,
) -> QuotaGuard:
    # Two fetchrow results: the first answers `questions_today`, the second the
    # upload count. Each test only exercises one of them.
    pool = FakePool(fetchrow=[{"n": asked}, {"n": uploaded}])
    usage = UsageRepository(cast(Any, pool))
    return QuotaGuard(
        cast(Any, pool),
        usage,
        cast(Any, StubAccounts(unlimited)),
        daily_questions=questions,
        daily_documents=documents,
    )


class StubAccounts:
    """Stands in for the allowlist lookup, which is tested on its own."""

    def __init__(
        self,
        unlimited: bool,
        account: Account | None = _USABLE,
        subject: str | None = None,
    ) -> None:
        self._unlimited = unlimited
        self._account = account
        self._subject = subject

    async def is_unlimited(self, user_id: UUID) -> bool:
        return self._unlimited

    async def get(self, user_id: UUID) -> Account | None:
        return self._account

    async def subject(self, user_id: UUID) -> str | None:
        """`None` by default, which is a deployment with no pepper configured.

        That is the pre-migration-0013 behaviour — count per account, and only
        per account — so every test below that does not pass a subject still
        measures the rule it was written for.
        """
        return self._subject


# --- who is allowed to spend at all -------------------------------------------
#
# `Account.usable` existed from the start and only the unlimited-exemption check
# ever read it, so it denied a privilege while the ordinary paths stayed open.
# These pin it to the two paths that spend money.


def _unusable_guard(account: Account | None) -> QuotaGuard:
    pool = FakePool(fetchrow=[{"n": 0}, {"n": 0}])
    return QuotaGuard(
        cast(Any, pool),
        UsageRepository(cast(Any, pool)),
        cast(Any, StubAccounts(False, account)),
        daily_questions=3,
        daily_documents=1,
    )


@pytest.mark.parametrize(
    "account",
    [_BANNED, _DELETED, _ANONYMOUS, None],
    ids=["banned", "deleted", "anonymous", "no-such-account"],
)
async def test_an_unusable_account_cannot_ask(account: Account | None) -> None:
    with pytest.raises(AccountNotUsableError):
        await _unusable_guard(account).ensure_can_ask(USER)


@pytest.mark.parametrize(
    "account",
    [_BANNED, _DELETED, _ANONYMOUS, None],
    ids=["banned", "deleted", "anonymous", "no-such-account"],
)
async def test_an_unusable_account_cannot_upload(account: Account | None) -> None:
    """The expensive half. Anonymous ids are free to mint, and every allowance
    in this system is keyed to one, so an open upload path here is an unbounded
    number of daily allowances against a single global budget."""
    with pytest.raises(AccountNotUsableError):
        await _unusable_guard(account).ensure_can_upload(USER)


async def test_being_unusable_is_not_a_quota_and_says_so() -> None:
    """403, and no `Retry-After`: nothing about this resets at midnight, and
    telling a banned account to come back tomorrow is advice, not a limit."""
    with pytest.raises(AccountNotUsableError) as caught:
        await _unusable_guard(_BANNED).ensure_can_ask(USER)

    assert caught.value.as_http().status_code == 403
    assert caught.value.retry_after_seconds is None


async def test_the_exemption_cannot_rescue_an_unusable_account() -> None:
    """Order matters: a banned address left on the allowlist must not walk past
    the check by being unlimited."""
    pool = FakePool(fetchrow=[{"n": 0}, {"n": 0}])
    guard = QuotaGuard(
        cast(Any, pool),
        UsageRepository(cast(Any, pool)),
        cast(Any, StubAccounts(True, _BANNED)),
        daily_questions=3,
        daily_documents=1,
    )

    with pytest.raises(AccountNotUsableError):
        await guard.ensure_can_ask(USER)


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
        cast(Any, StubAccounts(False)),
        daily_questions=10,
        daily_documents=10,
    )

    await guard.ensure_can_upload(USER)

    assert "not is_sample" in pool.queries[0]


async def test_a_document_that_failed_does_not_spend_the_daily_allowance() -> None:
    """Asserted on the SQL, like the sample exclusion above, and for a reason
    that was not hypothetical.

    The first real policy anyone uploaded failed on our side — this client was
    exceeding an embedding quota by itself — and the failed row spent the
    uploader's single daily document. They could not retry until midnight UTC
    because of our bug. A quota prices a service rendered; nothing was.
    """
    pool = FakePool(fetchrow=[{"n": 0}])
    guard = QuotaGuard(
        cast(Any, pool),
        UsageRepository(cast(Any, pool)),
        cast(Any, StubAccounts(False)),
        daily_questions=10,
        daily_documents=1,
    )

    await guard.ensure_can_upload(USER)

    assert "status <> 'failed'" in pool.queries[0]


async def test_an_allowlisted_account_is_not_counted() -> None:
    """The owner's own account, so the demo can be tested without burning it.

    Note what is *not* consulted: the token. Whether an account is exempt is
    decided against the account row (`api/accounts.py`), so this guard only ever
    sees the answer, never the address.
    """
    guard = _guard(asked=99, uploaded=99, unlimited=True)

    await guard.ensure_can_ask(USER)
    await guard.ensure_can_upload(USER)


async def test_the_allowance_reports_unlimited_as_none_not_zero() -> None:
    """Zero left and no limit at all must not render the same."""
    allowance = await _guard(asked=99, unlimited=True).allowance(USER)

    assert allowance.unlimited is True
    assert allowance.questions_left is None
    assert allowance.documents_left is None


async def test_the_allowance_counts_down_and_stops_at_zero() -> None:
    allowance = await _guard(asked=2, uploaded=1, questions=3, documents=1).allowance(USER)

    assert allowance.questions_left == 1
    assert allowance.documents_left == 0


async def test_the_allowance_never_reports_a_negative_remainder() -> None:
    """A count can exceed the limit — concurrent requests land together."""
    allowance = await _guard(asked=9, questions=3).allowance(USER)

    assert allowance.questions_left == 0


# -----------------------------------------------------------------------------
# the allowance survives deleting the account
# -----------------------------------------------------------------------------
#
# The hole these close, in the order it happened: delete the account, sign in
# again with the same Google account, and Supabase mints a new user id.
# `usage_events.user_id` is already null (migration 0004 sets it null rather
# than cascading, so the spend stays on the breaker's books) and `documents`
# has cascaded away, so both per-account counts read zero and the daily limit
# is fresh. Repeat for an unlimited allowance.
#
# `identity_quota` (migration 0013) is counted per Google identity instead, and
# the guard takes the larger of the two.

SUBJECT = "b7cc2f00deadbeef"


def _identity_guard(
    *,
    subject: str | None = SUBJECT,
    reserved: bool = True,
    ledger: int = 0,
    questions: int = 3,
    documents: int = 1,
) -> tuple[QuotaGuard, FakePool]:
    """A guard whose two counts can be set independently.

    Row order mirrors the guard: the per-account count is read first, then the
    reserve statement decides. `reserved=False` is the reserve returning no row,
    which is how the statement says the identity is already at its limit.
    """
    rows: list[dict[str, object] | None] = [{"n": ledger}]
    if subject is not None:
        rows.append({"questions": 1} if reserved else None)
    pool = FakePool(fetchrow=rows)
    return (
        QuotaGuard(
            cast(Any, pool),
            UsageRepository(cast(Any, pool)),
            cast(Any, StubAccounts(False, subject=subject)),
            daily_questions=questions,
            daily_documents=documents,
        ),
        pool,
    )


async def test_a_fresh_account_still_carries_the_identitys_questions() -> None:
    """The ledger says zero because the old account is gone. The limit holds.

    This is the whole vulnerability in one test: a brand new user id, nothing
    of theirs in `usage_events`, and the question is still refused.
    """
    guard, _ = _identity_guard(reserved=False, ledger=0, questions=3)

    with pytest.raises(DailyQuotaExceededError):
        await guard.ensure_can_ask(USER)


async def test_a_fresh_account_still_carries_the_identitys_uploads() -> None:
    guard, _ = _identity_guard(reserved=False, ledger=0, documents=1)

    with pytest.raises(DailyQuotaExceededError):
        await guard.ensure_can_upload(USER)


async def test_the_slot_is_taken_in_the_same_statement_that_checks_it() -> None:
    """Counting and then incrementing leaves a window two requests fit through.

    The reserve is one statement — `on conflict ... where counter < limit` —
    so Postgres' own row lock decides which of two simultaneous questions gets
    the last slot. This pins the shape rather than the race, which a unit test
    cannot stage.
    """
    guard, pool = _identity_guard(ledger=0)

    await guard.ensure_can_ask(USER)

    reserve = pool.queries[-1]
    assert "insert into identity_quota" in reserve
    assert "where identity_quota.questions < $2" in reserve
    assert "returning questions" in reserve


async def test_either_count_alone_can_stop_a_spender() -> None:
    """Neither may rescue somebody the other has already stopped."""
    ledger_full, _ = _identity_guard(ledger=3, reserved=True, questions=3)
    identity_full, _ = _identity_guard(ledger=0, reserved=False, questions=3)

    for guard in (ledger_full, identity_full):
        with pytest.raises(DailyQuotaExceededError):
            await guard.ensure_can_ask(USER)


async def test_without_a_subject_the_per_account_count_still_binds() -> None:
    """A deployment with no pepper is the old behaviour, not an open door.

    It loses the protection against deletion and keeps everything else, which
    is why `/api/health` reports a missing pepper and a deployed environment
    refuses to boot without one.
    """
    guard, _ = _identity_guard(subject=None, ledger=3, questions=3)

    with pytest.raises(DailyQuotaExceededError):
        await guard.ensure_can_ask(USER)


async def test_an_unreachable_counter_does_not_refuse_every_question() -> None:
    """It runs before the work, so failing closed would close the demo.

    The per-account count still binds; what is lost is only the protection
    against a deleted account, which is the smaller of the two failures.
    """

    class FailingPool(FakePool):
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "identity_quota" in query:
                raise RuntimeError("no")
            return await super().fetchrow(query, *args)

    pool = FailingPool(fetchrow=[{"n": 0}])
    guard = QuotaGuard(
        cast(Any, pool),
        UsageRepository(cast(Any, pool)),
        cast(Any, StubAccounts(False, subject=SUBJECT)),
        daily_questions=3,
        daily_documents=1,
    )

    await guard.ensure_can_ask(USER)  # does not raise


async def test_a_failed_refund_never_fails_the_request() -> None:
    """The answer is already served. Losing the refund beats losing that."""

    class FailingPool(FakePool):
        async def execute(self, query: str, *args: object) -> None:
            raise RuntimeError("no")

    pool = FailingPool()
    guard = QuotaGuard(
        cast(Any, pool),
        UsageRepository(cast(Any, pool)),
        cast(Any, StubAccounts(False, subject=SUBJECT)),
        daily_questions=3,
        daily_documents=1,
    )

    await guard.refund_question(USER)  # does not raise


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
