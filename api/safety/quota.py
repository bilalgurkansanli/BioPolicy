"""Per-user daily limits.

The demo is public and every question costs real money, so one visitor must not
be able to spend the whole allowance. These are the polite limits; the budget
breaker is the impolite one.

## Two questions, in this order

**May this account spend at all?** Banned, deleted and anonymous accounts may
not, and until recently nothing asked: `Account.usable` was computed and only
ever consulted to deny the exemption below, so it withheld a privilege while
leaving the ordinary paths open. The anonymous case is the costly one — every
limit here is keyed to a user id, and an anonymous id can be minted in a loop.

**Then, is it within its allowance?** The owner's own address is allowlisted so
the demo can be tested without burning three questions a day. The exemption is
decided in `api/accounts.py` against the account row rather than the token, and
both questions are asked in exactly the two places below — there is no third
path that spends money.

## Where the counts come from

Questions are counted from `usage_events` (`operation = 'answer'`), uploads from
`documents`. Both are the records the work actually produced, rather than a
separate counter that can drift from reality — a counter that says 40 while the
ledger says 200 is worse than no counter.

The cost of that choice is stated rather than hidden: usage is recorded *after*
a call completes, so a burst of simultaneous requests is counted once they land.
The limit binds over a day, not over a second; rate limiting is a different
control and is not implemented here.

## Why there is now a second count as well

Both records above hang off the account, and an account is something its owner
can delete. Do that and sign in again with the same Google account: Supabase
mints a new id, `usage_events.user_id` is already null and `documents` has
cascaded, so every counter here reads zero and the allowance is fresh. It was an
unlimited allowance for anyone willing to click twice — measured on the
development project, three answers sitting under a null user while a live
account held a full quota.

`identity_quota` (migration 0013) is the durable half: keyed on an HMAC of
Google's `sub` rather than on the row, so it outlives the account.

## Reserved before the work, not counted after it

The two guards below take a slot from it *before* anything is spent, in a single
statement that increments only while the counter is under the limit. That is one
more property than the ledger can offer: counting first and incrementing second
leaves a window, and two requests that land inside it both read the same number
and both proceed. Here Postgres' own row lock on the conflicting insert decides
which of them gets the last slot.

Reserving up front means every path that takes a slot and then does not spend
has to give it back, and there are four: an answer served from cache, a question
the retrieval floor refuses before any model is called, a provider that failed,
and an ingest that never produced a readable document. `refund_question` and
`refund_document` are those paths. Without them the allowance would count
attempts, and the first thing anyone would notice is that our failures cost them
their day — which is the exact complaint `_documents_today` already excludes
`failed` to avoid.

## Both counts, and why neither is dropped

The ledger still binds first. It cannot drift, because it is the record of the
work itself rather than a number kept alongside it, and on a deployment with no
pepper configured it is the whole limit. The identity counter binds second and
is the only one that remembers after a deletion. A spender has to get past both.

Their failure modes are deliberately opposite. A missing ledger row costs
nothing, because the counter still holds. An unreachable `identity_quota` lets
the question through, because this check runs *before* the work and failing
closed would refuse every question in the demo over a table that exists to stop
a resettable allowance — the ledger is still there, and the log line is what
keeps the degradation visible rather than silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

from api.accounts import AccountRepository
from api.logging_config import get_logger
from api.safety.limits import AccountNotUsableError, DailyQuotaExceededError
from api.usage import UsageRepository

log = get_logger(__name__)

# Seconds until the next UTC midnight is close enough for a retry hint, and a
# fixed value keeps the message from implying more precision than it has.
RETRY_AFTER_SECONDS = 60 * 60

# One statement per counter, written out rather than composed from a column
# name: this is a spending limit, and an f-string with a column in it is the
# shape that stops being safe the day somebody adds a third caller.
#
# `where identity_quota.<counter> < $2` is what makes the read and the write a
# single statement, so the row lock Postgres already takes when two inserts
# conflict is what decides which of two simultaneous requests gets the slot.
#
# A limit that is already reached returns no row: `on conflict do update` with a
# false `where` updates nothing, inserts nothing and raises nothing. That empty
# result is the refusal.
#
# The insert branch is not guarded by the limit because it cannot need to be —
# the callers below refuse a limit of zero before reaching here, and every other
# limit admits a first row.
_RESERVE_QUESTION = """
    insert into identity_quota (subject, day, questions)
    values ($1, (now() at time zone 'utc')::date, 1)
    on conflict (subject, day) do update
       set questions = identity_quota.questions + 1, updated_at = now()
     where identity_quota.questions < $2
    returning questions
"""

_RESERVE_DOCUMENT = """
    insert into identity_quota (subject, day, documents)
    values ($1, (now() at time zone 'utc')::date, 1)
    on conflict (subject, day) do update
       set documents = identity_quota.documents + 1, updated_at = now()
     where identity_quota.documents < $2
    returning documents
"""

# `greatest(.., 0)` because a refund that ran twice must not hand out a fourth
# question. There is no path that refunds twice today; the floor is here so that
# adding one is a bug that costs nothing rather than a bug that grants an
# allowance.
_REFUND_QUESTION = """
    update identity_quota
       set questions = greatest(questions - 1, 0), updated_at = now()
     where subject = $1 and day = (now() at time zone 'utc')::date
"""

_REFUND_DOCUMENT = """
    update identity_quota
       set documents = greatest(documents - 1, 0), updated_at = now()
     where subject = $1 and day = (now() at time zone 'utc')::date
"""


@dataclass(frozen=True, slots=True)
class Allowance:
    """What one account has left today. Also what the interface renders."""

    unlimited: bool
    questions_used: int
    questions_limit: int
    documents_used: int
    documents_limit: int

    @property
    def questions_left(self) -> int | None:
        """`None` means unlimited — distinct from zero, and never shown as one."""
        return None if self.unlimited else max(0, self.questions_limit - self.questions_used)

    @property
    def documents_left(self) -> int | None:
        return None if self.unlimited else max(0, self.documents_limit - self.documents_used)


class QuotaGuard:
    def __init__(
        self,
        pool: asyncpg.Pool,
        usage: UsageRepository,
        accounts: AccountRepository,
        *,
        daily_questions: int,
        daily_documents: int,
    ) -> None:
        self._pool = pool
        self._usage = usage
        self._accounts = accounts
        self._daily_questions = daily_questions
        self._daily_documents = daily_documents

    async def _identity_counts(self, user_id: UUID) -> tuple[int, int]:
        """Today's (questions, documents) for the identity behind this account.

        `(0, 0)` when there is no subject to count under — no pepper configured,
        or no Google identity on the row. That is not a grant: it leaves the
        per-account counts to bind on their own, which is what they did before
        this table existed.
        """
        subject = await self._accounts.subject(user_id)
        if subject is None:
            return (0, 0)

        row = await self._pool.fetchrow(
            """
            select questions, documents from identity_quota
             where subject = $1 and day = (now() at time zone 'utc')::date
            """,
            subject,
        )
        return (int(row["questions"]), int(row["documents"])) if row else (0, 0)

    async def _reserve(self, user_id: UUID, *, statement: str, limit: int) -> bool:
        """Take one slot from today's identity allowance, or report there is none.

        The read and the write are one statement, which is the point. Counting
        first and incrementing afterwards leaves a window between them, and two
        requests that land inside it both read the same number and both proceed
        — the burst the module docstring above admits the ledger cannot catch.
        Here the row lock Postgres already takes on a conflicting insert decides
        which of them gets the slot.

        `True` when there is nothing to reserve against: no pepper configured, or
        no Google identity. That is not a grant — the per-account count has
        already been consulted by the caller and it is still binding. It only
        means this second, durable limit has nothing to say.

        A failure to reach the table is also `True`, and deliberately so. This
        runs before the work rather than after it, so an unreachable counter
        would otherwise refuse every question in the demo over a table that
        exists to stop a resettable allowance. The ledger still binds; the log
        line is what keeps the degradation visible.
        """
        subject = await self._accounts.subject(user_id)
        if subject is None:
            return True

        try:
            row = await self._pool.fetchrow(statement, subject, limit)
        except Exception as exc:
            log.error("identity_quota_unavailable", error=str(exc))
            return True

        return row is not None

    async def _refund(self, user_id: UUID, *, statement: str, kind: str) -> None:
        """Give a reserved slot back, because nothing was actually spent.

        Reserving happens before the work, so every path that takes a slot and
        then does not spend has to return it: an answer served from cache, a
        question refused by the retrieval floor before any model is called, a
        provider that failed, an ingest that died. Without this the allowance
        would be a count of *attempts*, and the first thing a user would notice
        is that our own failures cost them their day.

        Never raises. A refund that does not land costs somebody one question;
        an exception here would cost them the answer they already have.
        """
        subject = await self._accounts.subject(user_id)
        if subject is None:
            return

        try:
            await self._pool.execute(statement, subject)
        except Exception as exc:
            log.error("identity_quota_not_refunded", kind=kind, error=str(exc))

    async def refund_question(self, user_id: UUID) -> None:
        """A reserved question that was never asked of a model."""
        await self._refund(user_id, statement=_REFUND_QUESTION, kind="questions")

    async def refund_document(self, user_id: UUID) -> None:
        """A reserved upload whose ingestion did not produce a readable document.

        The per-account count already excludes `failed` — an ingest that died on
        our side must not spend somebody's one upload for the day — and this is
        the same rule applied to the counter that outlives the account. Without
        it the two would disagree, and `max` would make the harsher one bind.
        """
        await self._refund(user_id, statement=_REFUND_DOCUMENT, kind="documents")

    async def allowance(self, user_id: UUID) -> Allowance:
        """The whole picture for one account, in one place.

        The interface needs this to disable its composer at zero rather than
        letting someone type a question that will be refused. It is a *display*
        of the limit and never the limit itself — every spending path re-checks
        below, because a client that lies about what it was told must not be
        able to spend anything.
        """
        unlimited = await self._accounts.is_unlimited(user_id)
        return Allowance(
            unlimited=unlimited,
            questions_used=await self._questions_used(user_id),
            questions_limit=self._daily_questions,
            documents_used=await self._documents_used(user_id),
            documents_limit=self._daily_documents,
        )

    async def _questions_used(self, user_id: UUID) -> int:
        """Answers today, by both counts, larger wins."""
        identity, _ = await self._identity_counts(user_id)
        return max(await self._usage.questions_today(user_id), identity)

    async def _documents_used(self, user_id: UUID) -> int:
        """Documents today, by both counts, larger wins."""
        _, identity = await self._identity_counts(user_id)
        return max(await self._documents_today(user_id), identity)

    async def ensure_usable(self, user_id: UUID) -> None:
        """Refuse an account that is banned, deleted, or anonymous.

        `Account.usable` computed this from the start and nothing consulted it
        except the unlimited-exemption check, so the flag denied a *privilege*
        while the ordinary paths stayed open. Two consequences, and the second
        is the expensive one:

        * A ban took effect only when the access token expired, because the
          token verifies on its signature and never asks whether the account
          behind it still exists.
        * Every limit here is per user id, and an anonymous id costs nothing to
          create. With the provider enabled, a loop of anonymous sign-ins is an
          unbounded number of daily allowances against a single global budget.

        A missing row is refused rather than allowed. It means the token names
        an account `auth.users` does not have, which is not a state a spending
        path should resolve in the caller's favour.
        """
        account = await self._accounts.get(user_id)
        if account is not None and account.usable:
            return

        log.warning(
            "account_not_usable",
            user_id=str(user_id),
            reason="missing" if account is None else "banned_deleted_or_anonymous",
        )
        raise AccountNotUsableError(
            "This account cannot use the demo. Sign in with Google to continue."
        )

    async def ensure_can_ask(self, user_id: UUID) -> None:
        await self.ensure_usable(user_id)
        if await self._accounts.is_unlimited(user_id):
            return

        # Two counts, asked in the order of their certainty. The ledger cannot
        # drift and is the whole limit on a deployment with no pepper; the
        # identity counter is the one that survives a deletion, and reserving
        # from it is what makes the decision atomic.
        asked = await self._usage.questions_today(user_id)
        within_ledger = asked < self._daily_questions
        if within_ledger and await self._reserve(
            user_id, statement=_RESERVE_QUESTION, limit=self._daily_questions
        ):
            return

        log.info("quota_exceeded", kind="questions", user_id=str(user_id), asked=asked)
        raise DailyQuotaExceededError(
            f"You have reached the daily limit of {self._daily_questions} questions "
            f"for this demo. It resets at midnight UTC.",
            retry_after_seconds=RETRY_AFTER_SECONDS,
        )

    async def ensure_can_upload(self, user_id: UUID) -> None:
        await self.ensure_usable(user_id)
        if await self._accounts.is_unlimited(user_id):
            return

        # As above: the ledger decides, and the reserve makes it atomic. The
        # slot is given back by `refund_document` if ingestion never produces a
        # readable document, which is what keeps a failure on our side from
        # spending somebody's one upload for the day.
        uploaded = await self._documents_today(user_id)
        within_ledger = uploaded < self._daily_documents
        if within_ledger and await self._reserve(
            user_id, statement=_RESERVE_DOCUMENT, limit=self._daily_documents
        ):
            return

        log.info("quota_exceeded", kind="documents", user_id=str(user_id), uploaded=uploaded)
        raise DailyQuotaExceededError(
            f"You have reached the daily limit of {self._daily_documents} documents "
            f"for this demo. It resets at midnight UTC.",
            retry_after_seconds=RETRY_AFTER_SECONDS,
        )

    async def _documents_today(self, user_id: UUID) -> int:
        """Documents this account uploaded today that we actually processed.

        `failed` is excluded, and the reason is a real one rather than a
        courtesy. The first genuine policy anyone uploaded failed on our side —
        an embedding quota this client was exceeding by itself — and the row it
        left behind spent the uploader's single daily document. They could not
        retry until midnight UTC, because of our bug.

        A quota is a price for a service rendered. Nothing was rendered here, so
        nothing is owed. Repeatedly failing uploads is not a way around the
        limit either: the work before the failure is local parsing, and the one
        part that does cost money — OCR — is capped per document and watched by
        the budget breaker.
        """
        row = await self._pool.fetchrow(
            """
            select count(*) as n from documents
             where user_id = $1
               and not is_sample
               and status <> 'failed'
               and created_at >= date_trunc('day', now() at time zone 'utc')
            """,
            user_id,
        )
        return int(row["n"]) if row else 0
