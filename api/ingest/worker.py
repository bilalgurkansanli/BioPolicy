"""Taking work off the queue and running it.

Two callers, deliberately: the upload endpoint fires this in-process as the fast
path, and pg_cron calls `/api/internal/process-queue` as the watchdog. ADR 007
explains why both exist — a scale-to-zero container can be reclaimed the moment
it returns its response, so an in-process task is an optimisation and never the
durable mechanism.

The watchdog no longer runs on a schedule at all. On Fluid compute a timed call
is not a cheap poll — it wakes a container that is then billed for a five-minute
minimum whether or not there was work — so migrations 0015 and 0016 moved the
trigger off the clock and onto real traffic. `api/maintenance.py` drains the
queue on a request that has already paid for the container.

The consequence is that the in-process fast path does nearly all the work, and a
document stranded by a killed instance waits for the next visitor rather than
for a timer.

They race, and that is fine. `claim_next_document()` uses `FOR UPDATE SKIP
LOCKED`, so whichever transaction arrives first takes the row and the other
walks past it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from api.documents import DocumentRepository
from api.ingest.pipeline import IngestionPipeline
from api.logging_config import get_logger
from api.storage import DocumentStorage, StorageError

log = get_logger(__name__)

# How many documents one sweep will process. Bounded because the sweep runs
# inside a request with a wall-clock limit, and because a backlog is better
# worked through over several minutes than dropped when the function is killed.
MAX_PER_SWEEP = 3


class IngestionWorker:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        pipeline: IngestionPipeline,
        storage: DocumentStorage,
        on_failed: Callable[[UUID], Awaitable[None]] | None = None,
    ) -> None:
        self._documents = documents
        self._pipeline = pipeline
        self._storage = storage
        # Called with the owner's user id whenever a document ends up `failed`,
        # so the upload slot reserved at `POST /documents` can be given back.
        # `QuotaGuard.refund_document` in the running application; `None`
        # wherever the worker is exercised without a quota.
        #
        # It lives here rather than in the pipeline because this is the one
        # place that sees every ending: `run_safely` turns its own failures into
        # `None`, and the storage failure below is the worker's own. Two hooks
        # in two files would be two places to forget.
        self._on_failed = on_failed

    async def _failed(self, user_id: UUID) -> None:
        if self._on_failed is not None:
            await self._on_failed(user_id)

    async def process_next(self) -> bool:
        """Claim and ingest one document. Returns whether there was work."""
        record = await self._documents.claim_next()
        if record is None:
            return False

        log.info(
            "ingest_claimed",
            document_id=str(record.id),
            attempt=record.attempts,
            filename=record.filename,
        )

        try:
            data = await self._storage.download(record.storage_path)
        except StorageError as exc:
            # The row exists and the object does not. Retrying will not conjure
            # it, so this is terminal rather than left to exhaust its attempts
            # and occupy the queue for the next five minutes.
            log.error("ingest_object_missing", document_id=str(record.id), error=str(exc))
            await self._documents.mark_failed(
                record.id,
                "The uploaded file could not be read back from storage. "
                "Please try uploading it again.",
            )
            await self._failed(record.user_id)
            return True

        # `run_safely` turns every failure into a user-safe message on the row.
        # A raised exception here would leave the document claimed and stuck
        # until the stale threshold, which is the slowest possible failure.
        #
        # The slot comes back when the failure was ours — nothing was rendered,
        # so nothing is owed. It does *not* come back when the file itself was
        # the problem: a refunded rejection is a rejection that costs the sender
        # nothing to repeat, and 25MB of storage plus a worker slot per attempt
        # is not nothing to us.
        async def settle(blame_input: bool) -> None:
            if not blame_input:
                await self._failed(record.user_id)

        await self._pipeline.run_safely(record, data, on_failure=settle)
        return True

    async def drain(self, *, max_documents: int = MAX_PER_SWEEP) -> int:
        processed = 0
        while processed < max_documents and await self.process_next():
            processed += 1
        return processed
