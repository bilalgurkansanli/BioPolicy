"""The 24-hour deletion promise, enforced.

The promise is printed on the workspace in two languages, which makes it a
commitment rather than a backlog item. This module is what makes it true, and
the ordering inside `purge_expired` is the whole point:

    storage object → database rows → audit entry

Deleting the rows first is the tempting order — one statement, `on delete
cascade` takes the chunks, done. It also loses the storage path, and with it any
way to find the PDF still sitting in the bucket. The audit table would record a
successful purge, the tests would pass, and the user's policy would still be on
disk. Migration 0007 carries the same reasoning for the same reason: this is the
mistake that looks like it worked.

So a document whose file could not be deleted keeps its row and is retried on
the next sweep. A row without its file is the one state this must never produce.

## Except that something else produces it

Migration 0007 also schedules `purge_expired_rows()`, a database-side fallback
for the case where this API is down longer than the retention window. It deletes
rows and cannot touch the bucket, so it produces exactly the state above: a file
with no row, no owner and no timer. The migration says it is "reconciled by the
API's own sweep" — and until `reconcile_orphans` below, no such sweep existed.
On the development project it had run 5 times and left 6 PDFs in the bucket, the
oldest 5 days past its deletion date.

That is why reconciliation reads `storage.objects` rather than the `documents`
table: once the row is gone, the row is not where the evidence is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import asyncpg

from api.logging_config import get_logger
from api.storage import DocumentStorage

log = get_logger(__name__)

# Sweeps run every 15 minutes, so a batch only has to cover a quarter hour of
# expiries. Bounded so one sweep cannot run for minutes on a serverless clock.
PURGE_BATCH_SIZE = 100

# How old an unreferenced object must be before it counts as abandoned.
#
# Upload is: create the row, hand out a signed URL, browser uploads, confirm. The
# row therefore exists before the object does, and an unreferenced object is
# already anomalous. The hour is margin for the reverse case — a row rolled back
# after an upload landed — and it is six times the signed URL's own lifetime. It
# stays far below the retention window so a genuine orphan is collected within
# the promise rather than a day after it.
#
# A `timedelta`, not the string `'1 hour'`: asyncpg maps `interval` to
# `timedelta` in both directions, and a string reaches the driver as a type
# error naming `'str' object has no attribute 'days'` — which is caught by the
# scan's own error handler and degrades to "no orphans found". The fakes cannot
# see this; only running it against Postgres can.
ORPHAN_GRACE_INTERVAL = timedelta(hours=1)


@dataclass(slots=True)
class PurgeReport:
    purged: int = 0
    chunks_deleted: int = 0
    failed: int = 0
    orphans_deleted: int = 0

    @property
    def as_dict(self) -> dict[str, int]:
        return {
            "purged": self.purged,
            "chunks_deleted": self.chunks_deleted,
            "failed": self.failed,
            "orphans_deleted": self.orphans_deleted,
        }


class RetentionService:
    def __init__(self, pool: asyncpg.Pool, storage: DocumentStorage) -> None:
        self._pool = pool
        self._storage = storage

    async def purge_expired(self, *, limit: int = PURGE_BATCH_SIZE) -> PurgeReport:
        rows = await self._pool.fetch(
            """
            select id, user_id, storage_path from documents
             where expires_at < now() and not is_sample
             order by expires_at
             limit $1
            """,
            limit,
        )
        report = PurgeReport()
        for row in rows:
            if await self._purge_one(row["id"], row["user_id"], row["storage_path"]):
                report.purged += 1
            else:
                report.failed += 1

        report.orphans_deleted = await self.reconcile_orphans()

        if report.purged or report.failed or report.orphans_deleted:
            log.info("retention_sweep", **report.as_dict)
        return report

    async def reconcile_orphans(self, *, limit: int = PURGE_BATCH_SIZE) -> int:
        """Delete bucket objects that no document row refers to.

        The database-side fallback in migration 0007 deletes rows it cannot
        match with files. Without this, those files stay indefinitely: nothing
        expires them, because expiry is a column on a row that no longer exists.

        Scoped to `uploads/` so it can only ever reach user uploads. Samples are
        never expired, so a sample object is not an orphan — but the scope means
        that even a bug in the join cannot delete one.

        No audit row is written here. `retention_audit` records the purge of a
        *document*, and by this point there is no document id to record — the
        count goes to the log and to the endpoint's response instead.
        """
        try:
            rows = await self._pool.fetch(
                """
                select o.name from storage.objects o
                 where o.bucket_id = $1
                   and o.name like 'uploads/%'
                   and o.created_at < now() - $2::interval
                   and not exists (
                     select 1 from documents d where d.storage_path = o.name
                   )
                 order by o.created_at
                 limit $3
                """,
                self._storage.bucket,
                ORPHAN_GRACE_INTERVAL,
                limit,
            )
        except Exception as exc:
            # Reading storage metadata is a privilege this service has but does
            # not control. Losing it must degrade reconciliation, not the purge.
            log.error("retention_orphan_scan_failed", error=str(exc))
            return 0

        deleted = 0
        for row in rows:
            if await self._storage.remove(row["name"]):
                deleted += 1
                log.info("retention_orphan_removed", path=row["name"])
            else:
                log.error("retention_orphan_failed", path=row["name"])
        return deleted

    async def purge_document(self, document_id: UUID) -> bool:
        """Delete one document now, on its owner's request.

        Same order, same guarantee. A user who asks for deletion before the 24
        hours are up gets the identical treatment the timer would have given.
        """
        row = await self._pool.fetchrow(
            "select id, user_id, storage_path from documents where id = $1 and not is_sample",
            document_id,
        )
        if row is None:
            return False
        return await self._purge_one(row["id"], row["user_id"], row["storage_path"])

    async def purge_user_documents(self, user_id: UUID) -> bool:
        """Delete everything one account uploaded, on its owner's request.

        Returns False if any file survived. Account deletion depends on that
        answer: `on delete cascade` reaches every row a user owns but reaches
        nothing in the bucket, so an account removed while one of its PDFs was
        still there would leave a file with no row, no owner and no timer — the
        exact state the ordering in this module exists to prevent.
        """
        rows = await self._pool.fetch(
            "select id, storage_path from documents where user_id = $1 and not is_sample",
            user_id,
        )
        purged = True
        for row in rows:
            if not await self._purge_one(row["id"], user_id, row["storage_path"]):
                purged = False
        return purged

    async def _purge_one(self, document_id: UUID, user_id: UUID | None, storage_path: str) -> bool:
        # 1. The file first. If this fails the row survives and the next sweep
        #    tries again — a retained row is recoverable, a retained file with
        #    no row is not even findable.
        if not await self._storage.remove(storage_path):
            log.error("retention_storage_failed", document_id=str(document_id))
            return False

        # 2. Rows. `on delete cascade` takes chunks, conversations and messages.
        async with self._pool.acquire() as connection, connection.transaction():
            chunks = await connection.fetchval(
                "select count(*) from chunks where document_id = $1", document_id
            )
            await connection.execute("delete from documents where id = $1", document_id)

            # 3. The audit entry, written only once both halves succeeded. An
            #    audit row for a purge that did not happen is worse than none.
            await connection.execute(
                """
                insert into retention_audit (document_id, user_id, chunks_deleted, storage_deleted)
                values ($1, $2, $3, true)
                """,
                document_id,
                user_id,
                int(chunks or 0),
            )
        return True
