"""The `documents` table, which is also the ingestion queue (ADR 007).

Status is not decoration — it is the state machine the whole async design rests
on, and it is what the UI renders as a progress bar over real stages rather than
a spinner. Every transition goes through this module so the write is in one
place and `claimed_at` is always touched alongside it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from api.constants import STATUS_FAILED, STATUS_READY
from api.logging_config import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class DocumentRecord:
    id: UUID
    user_id: UUID
    filename: str
    storage_path: str
    byte_size: int
    status: str
    is_sample: bool
    page_count: int | None = None
    source_type: str | None = None
    detected_lang: str | None = None
    error_message: str | None = None
    attempts: int = 0
    injection_findings: list[dict[str, str]] | None = None
    """Instruction-shaped text found at ingest. `None` = never scanned, `[]` = clean."""

    @classmethod
    def from_row(cls, row: Any) -> DocumentRecord:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            filename=row["filename"],
            storage_path=row["storage_path"],
            byte_size=row["byte_size"],
            status=row["status"],
            is_sample=row["is_sample"],
            page_count=row["page_count"],
            source_type=row["source_type"],
            detected_lang=row["detected_lang"],
            error_message=row["error_message"],
            attempts=row["attempts"],
            # `.get`, not `[...]`, because not every source of a document row
            # carries this column: `claim_next_document()` returns a fixed row
            # type declared in migration 0006. A worker claiming a job has not
            # scanned it yet anyway, so absent and null mean the same thing there.
            injection_findings=(
                json.loads(raw) if isinstance(raw := row.get("injection_findings"), str) else raw
            ),
        )


class DocumentRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        user_id: UUID,
        filename: str,
        storage_path: str,
        byte_size: int,
        is_sample: bool = False,
        document_id: UUID | None = None,
    ) -> DocumentRecord:
        """Insert a queued document. This row is the durable record (ADR 007).

        `document_id` is supplied by the upload flow rather than generated here.
        The id is minted before the file exists, because it names the object in
        storage (`uploads/{user}/{id}.pdf`) — and a row whose id differs from
        the one in its own storage path hands the client an identifier that does
        not identify the document.

        Samples get a far-future expiry so the retention job never deletes the
        public demo out from under itself — migration 0002 has a CHECK
        constraint enforcing that, so getting it wrong fails loudly here rather
        than silently 24 hours later.
        """
        row = await self._pool.fetchrow(
            """
            insert into documents (
                id, user_id, filename, storage_path, byte_size, is_sample, expires_at
            ) values (
                coalesce($6, gen_random_uuid()), $1, $2, $3, $4, $5,
                case when $5 then now() + interval '100 years'
                     else now() + interval '24 hours' end
            )
            returning *
            """,
            user_id,
            filename,
            storage_path,
            byte_size,
            is_sample,
            document_id,
        )
        return DocumentRecord.from_row(row)

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        row = await self._pool.fetchrow("select * from documents where id = $1", document_id)
        return DocumentRecord.from_row(row) if row else None

    async def find_sample(self, storage_path: str) -> DocumentRecord | None:
        row = await self._pool.fetchrow(
            "select * from documents where storage_path = $1 and is_sample", storage_path
        )
        return DocumentRecord.from_row(row) if row else None

    async def find_by_path(self, storage_path: str) -> DocumentRecord | None:
        """Any document at this path, sample or not.

        The seeder needs this because the evaluation fixtures deliberately are
        not samples — they must not appear in the public picker — but they are
        still seeded and re-seeded by the same script.
        """
        row = await self._pool.fetchrow(
            "select * from documents where storage_path = $1", storage_path
        )
        return DocumentRecord.from_row(row) if row else None

    async def set_status(
        self,
        document_id: UUID,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        """Advance the state machine.

        `claimed_at` is refreshed on every working transition, which is what
        keeps a long but healthy ingest from looking stale to the watchdog and
        being claimed a second time mid-run.
        """
        await self._pool.execute(
            """
            update documents
               set status        = $2,
                   error_message = $3,
                   claimed_at    = case when $2 in ('ready', 'failed')
                                        then claimed_at else now() end
             where id = $1
            """,
            document_id,
            status,
            error_message,
        )
        log.info("document_status", document_id=str(document_id), status=status)

    async def set_metadata(
        self,
        document_id: UUID,
        *,
        page_count: int,
        source_type: str,
        detected_lang: str | None,
        injection_findings: list[dict[str, str]] | None = None,
    ) -> None:
        await self._pool.execute(
            """
            update documents
               set page_count = $2, source_type = $3, detected_lang = $4,
                   injection_findings = $5
             where id = $1
            """,
            document_id,
            page_count,
            source_type,
            detected_lang,
            json.dumps(injection_findings) if injection_findings is not None else None,
        )

    async def mark_ready(self, document_id: UUID) -> None:
        await self.set_status(document_id, STATUS_READY)

    async def mark_failed(self, document_id: UUID, user_message: str) -> None:
        """Record a failure with text safe to show a user.

        Never pass an exception string here. Migration 0002 carries a comment
        saying so for the same reason: this column is returned by
        `GET /documents/{id}` and reaches the browser.
        """
        await self.set_status(document_id, STATUS_FAILED, error_message=user_message)

    async def claim_next(self) -> DocumentRecord | None:
        """Take one document off the queue (ADR 007).

        Delegates to `claim_next_document()` in migration 0006, which does the
        `FOR UPDATE SKIP LOCKED` work — the reason the immediate task fired by
        the upload endpoint and the pg_cron sweep can race harmlessly.
        """
        row = await self._pool.fetchrow("select * from claim_next_document()")
        return DocumentRecord.from_row(row) if row and row["id"] else None
