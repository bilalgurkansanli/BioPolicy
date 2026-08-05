"""Per-user daily limits.

The demo is public and every question costs real money, so one visitor must not
be able to spend the whole allowance. These are the polite limits; the budget
breaker is the impolite one.

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

from uuid import UUID

import asyncpg

from api.logging_config import get_logger
from api.safety.limits import DailyQuotaExceededError
from api.usage import UsageRepository

log = get_logger(__name__)

# Seconds until the next UTC midnight is close enough for a retry hint, and a
# fixed value keeps the message from implying more precision than it has.
RETRY_AFTER_SECONDS = 60 * 60


class QuotaGuard:
    def __init__(
        self,
        pool: asyncpg.Pool,
        usage: UsageRepository,
        *,
        daily_questions: int,
        daily_documents: int,
    ) -> None:
        self._pool = pool
        self._usage = usage
        self._daily_questions = daily_questions
        self._daily_documents = daily_documents

    async def ensure_can_ask(self, user_id: UUID) -> None:
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
        row = await self._pool.fetchrow(
            """
            select count(*) as n from documents
             where user_id = $1
               and not is_sample
               and created_at >= date_trunc('day', now() at time zone 'utc')
            """,
            user_id,
        )
        uploaded = int(row["n"]) if row else 0
        if uploaded < self._daily_documents:
            return
        log.info("quota_exceeded", kind="documents", user_id=str(user_id), uploaded=uploaded)
        raise DailyQuotaExceededError(
            f"You have reached the daily limit of {self._daily_documents} documents "
            f"for this demo. It resets at midnight UTC.",
            retry_after_seconds=RETRY_AFTER_SECONDS,
        )
