"""Per-user daily limits.

The demo is public and every question costs real money, so one visitor must not
be able to spend the whole allowance. These are the polite limits; the budget
breaker is the impolite one.

## One account can be exempt

The owner's own address is allowlisted so the demo can be tested without
burning three questions a day. The exemption is decided in `api/accounts.py`
against the account row rather than the token, and it is checked in exactly the
two places below — there is no third path that spends money.

## Where the counts come from

Questions are counted from `usage_events` (`operation = 'answer'`), uploads from
`documents`. Both are the records the work actually produced, rather than a
separate counter that can drift from reality — a counter that says 40 while the
ledger says 200 is worse than no counter.

The cost of that choice is stated rather than hidden: usage is recorded *after*
a call completes, so a burst of simultaneous requests is counted once they land.
The limit binds over a day, not over a second; rate limiting is a different
control and is not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

from api.accounts import AccountRepository
from api.logging_config import get_logger
from api.safety.limits import DailyQuotaExceededError
from api.usage import UsageRepository

log = get_logger(__name__)

# Seconds until the next UTC midnight is close enough for a retry hint, and a
# fixed value keeps the message from implying more precision than it has.
RETRY_AFTER_SECONDS = 60 * 60


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
            questions_used=await self._usage.questions_today(user_id),
            questions_limit=self._daily_questions,
            documents_used=await self._documents_today(user_id),
            documents_limit=self._daily_documents,
        )

    async def ensure_can_ask(self, user_id: UUID) -> None:
        if await self._accounts.is_unlimited(user_id):
            return

        asked = await self._usage.questions_today(user_id)
        if asked < self._daily_questions:
            return
        log.info("quota_exceeded", kind="questions", user_id=str(user_id), asked=asked)
        raise DailyQuotaExceededError(
            f"You have reached the daily limit of {self._daily_questions} questions "
            f"for this demo. It resets at midnight UTC.",
            retry_after_seconds=RETRY_AFTER_SECONDS,
        )

    async def ensure_can_upload(self, user_id: UUID) -> None:
        if await self._accounts.is_unlimited(user_id):
            return

        uploaded = await self._documents_today(user_id)
        if uploaded < self._daily_documents:
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
