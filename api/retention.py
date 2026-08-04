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
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

from api.logging_config import get_logger
from api.storage import DocumentStorage

log = get_logger(__name__)

# Sweeps run every 15 minutes, so a batch only has to cover a quarter hour of
# expiries. Bounded so one sweep cannot run for minutes on a serverless clock.
PURGE_BATCH_SIZE = 100


@dataclass(slots=True)
class PurgeReport:
    purged: int = 0
    chunks_deleted: int = 0
    failed: int = 0

    @property
    def as_dict(self) -> dict[str, int]:
        return {
            "purged": self.purged,
            "chunks_deleted": self.chunks_deleted,
            "failed": self.failed,
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

        if report.purged or report.failed:
            log.info("retention_sweep", **report.as_dict)
        return report

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
