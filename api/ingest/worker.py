"""Taking work off the queue and running it.

Two callers, deliberately: the upload endpoint fires this in-process as the fast
path, and pg_cron calls `/api/internal/process-queue` every minute as the
watchdog. ADR 007 explains why both exist — a scale-to-zero container can be
reclaimed the moment it returns its response, so an in-process task is an
optimisation and never the durable mechanism.

They race, and that is fine. `claim_next_document()` uses `FOR UPDATE SKIP
LOCKED`, so whichever transaction arrives first takes the row and the other
walks past it.
"""

from __future__ import annotations

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
    ) -> None:
        self._documents = documents
        self._pipeline = pipeline
        self._storage = storage

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
            return True

        # `run_safely` turns every failure into a user-safe message on the row.
        # A raised exception here would leave the document claimed and stuck
        # until the stale threshold, which is the slowest possible failure.
        await self._pipeline.run_safely(record, data)
        return True

    async def drain(self, *, max_documents: int = MAX_PER_SWEEP) -> int:
        processed = 0
        while processed < max_documents and await self.process_next():
            processed += 1
        return processed
