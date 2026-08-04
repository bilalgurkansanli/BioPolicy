"""Documents: listing, upload, status, signed viewing URLs, deletion.

Sample documents are readable without an account — the public demo has to work
before anyone signs in. Everything else is owner-scoped, and the scoping is done
in SQL rather than left to RLS, because the API holds a service-role key and
bypasses every policy (see `api/retrieval/store.py`).

## The upload is three steps, and it has to be

Constraint C1: a 200-page policy exceeds a serverless request body limit, so the
file never transits this API.

    POST /documents/upload-url   → quota and size checked, signed URL issued
    (browser PUTs the file straight to storage)
    POST /documents              → object verified, row created, ingestion fired

The middle step is the only one that carries bytes and it does not touch this
process. The last step re-reads the object's real size from storage rather than
believing the client, because a row created for a file that never landed becomes
a queue entry that fails on every attempt.
"""

from __future__ import annotations

import asyncio
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, MaybeUser
from api.constants import PIPELINE_STAGES
from api.deps import Config, State
from api.logging_config import get_logger
from api.safety.limits import LimitExceededError
from api.storage import StorageError, upload_path

router = APIRouter(prefix="/documents", tags=["documents"])

# NOTE ON PARAMETER ORDER: FastAPI resolves dependencies in declaration order,
# so `CurrentUser` is declared before `State` on every closed route. Otherwise a
# request with no token gets a 503 when the database is unreachable — telling an
# unauthenticated caller about backend health, and leaving a client unable to
# tell "sign in" from "we are broken". `api/tests/test_auth.py` pins this.
log = get_logger(__name__)

MAX_FILENAME_CHARS = 200


class DocumentSummary(BaseModel):
    id: UUID
    filename: str
    page_count: int | None
    source_type: str | None
    detected_lang: str | None
    status: str
    is_sample: bool


class DocumentStatus(BaseModel):
    id: UUID
    status: str
    stage_index: int
    """Position in the pipeline, so the UI can render real progress."""

    stage_count: int
    page_count: int | None
    source_type: str | None
    detected_lang: str | None
    chunk_count: int
    error: str | None


class SignedUrl(BaseModel):
    url: str
    expires_in: int


# -----------------------------------------------------------------------------
# reading
# -----------------------------------------------------------------------------


@router.get("/samples", response_model=list[DocumentSummary], summary="Bundled samples")
async def samples(state: State) -> list[DocumentSummary]:
    """The three documents the demo serves without an upload or an account."""
    rows = await state.pool.fetch(
        "select id, filename, page_count, source_type, detected_lang, status, is_sample "
        "from documents where is_sample and status = 'ready' order by filename"
    )
    return [DocumentSummary(**dict(row)) for row in rows]


@router.get("/mine", response_model=list[DocumentSummary], summary="Your own documents")
async def mine(user: CurrentUser, state: State) -> list[DocumentSummary]:
    rows = await state.pool.fetch(
        "select id, filename, page_count, source_type, detected_lang, status, is_sample "
        "from documents where user_id = $1 and not is_sample order by created_at desc",
        user.id,
    )
    return [DocumentSummary(**dict(row)) for row in rows]


@router.get("/{document_id}", response_model=DocumentStatus, summary="Ingestion status")
async def document_status(document_id: UUID, state: State, user: MaybeUser) -> DocumentStatus:
    row = await state.pool.fetchrow(
        """
        select d.id, d.status, d.page_count, d.source_type, d.detected_lang,
               d.error_message, d.is_sample,
               (select count(*) from chunks c where c.document_id = d.id) as chunk_count
          from documents d
         where d.id = $1 and (d.is_sample or d.user_id = $2)
        """,
        document_id,
        user.id if user else None,
    )
    if row is None:
        # 404 rather than 403 for a document owned by someone else: whether an
        # id exists is not something a stranger should be able to probe.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such document.")

    stage = row["status"]
    return DocumentStatus(
        id=row["id"],
        status=stage,
        # 'failed' is terminal and not a step, so it reports as the last index
        # rather than -1 — a progress bar that jumps backwards on failure reads
        # as a bug.
        stage_index=(
            PIPELINE_STAGES.index(stage) if stage in PIPELINE_STAGES else len(PIPELINE_STAGES) - 1
        ),
        stage_count=len(PIPELINE_STAGES),
        page_count=row["page_count"],
        source_type=row["source_type"],
        detected_lang=row["detected_lang"],
        chunk_count=row["chunk_count"],
        error=row["error_message"],
    )


@router.get("/{document_id}/url", response_model=SignedUrl, summary="Signed viewing URL")
async def viewing_url(document_id: UUID, state: State, user: MaybeUser) -> SignedUrl:
    """A short-lived link the PDF viewer can fetch.

    The bucket is private, so the browser cannot read the object directly — and
    that is the point. A public bucket would leave every uploaded policy
    readable by URL while RLS carefully guarded the metadata around it.
    """
    row = await state.pool.fetchrow(
        "select storage_path from documents where id = $1 and (is_sample or user_id = $2)",
        document_id,
        user.id if user else None,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such document.")

    try:
        url = await state.storage.signed_view_url(row["storage_path"])
    except StorageError as exc:
        log.error("signed_url_failed", document_id=str(document_id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Could not produce a viewing link."
        ) from exc
    return SignedUrl(url=url, expires_in=state.storage_view_ttl)


# -----------------------------------------------------------------------------
# uploading
# -----------------------------------------------------------------------------


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=MAX_FILENAME_CHARS)
    byte_size: int = Field(gt=0)


class UploadTicket(BaseModel):
    document_id: UUID
    storage_path: str
    upload_url: str
    token: str
    expires_in: int
    max_bytes: int


@router.post(
    "/upload-url",
    response_model=UploadTicket,
    summary="Reserve an upload",
    status_code=status.HTTP_201_CREATED,
)
async def upload_url(
    user: CurrentUser, request: UploadRequest, state: State, settings: Config
) -> UploadTicket:
    """Check the limits, then hand back a URL the browser uploads to directly.

    No row is created here. A ticket that is never used should leave nothing
    behind — otherwise a visitor who opens the picker and cancels has spent a
    slot from their daily document quota.
    """
    if request.byte_size > settings.max_upload_bytes:
        megabytes = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "message": f"The limit is {megabytes} MB.",
            },
        )
    if not request.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "not_a_pdf", "message": "Only PDF files are accepted."},
        )

    try:
        await state.quota.ensure_can_upload(user.id)
    except LimitExceededError as exc:
        raise exc.as_http() from exc

    document_id = uuid4()
    path = upload_path(user.id, document_id)
    try:
        signed = await state.storage.signed_upload_url(path)
    except StorageError as exc:
        log.error("upload_url_failed", error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Could not start the upload."
        ) from exc

    return UploadTicket(
        document_id=document_id,
        storage_path=path,
        upload_url=signed.url,
        token=signed.token,
        expires_in=signed.expires_in,
        max_bytes=settings.max_upload_bytes,
    )


class ConfirmRequest(BaseModel):
    document_id: UUID
    filename: str = Field(min_length=1, max_length=MAX_FILENAME_CHARS)


class ConfirmedUpload(BaseModel):
    id: UUID
    status: str


@router.post(
    "",
    response_model=ConfirmedUpload,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Confirm an upload and queue it",
)
async def confirm_upload(
    user: CurrentUser, request: ConfirmRequest, state: State, settings: Config
) -> ConfirmedUpload:
    """Verify the object exists, create the row, and start ingestion.

    202 rather than 201: the document is queued, not ready. Returning 201 would
    imply a resource the client can immediately read chunks from, and the
    polling that follows would look like a bug rather than the design (ADR 007).
    """
    path = upload_path(user.id, request.document_id)

    stored = await state.storage.stat(path)
    if stored is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "upload_missing",
                "message": "That upload was not found. Please try again.",
            },
        )
    if stored.byte_size > settings.max_upload_bytes:
        # Checked again against the *real* size: the ticket was issued on a
        # number the client supplied, and the client is not the authority on
        # what it actually uploaded.
        await state.storage.remove(path)
        megabytes = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "file_too_large", "message": f"The limit is {megabytes} MB."},
        )

    try:
        await state.quota.ensure_can_upload(user.id)
    except LimitExceededError as exc:
        await state.storage.remove(path)
        raise exc.as_http() from exc

    record = await state.documents.create(
        document_id=request.document_id,
        user_id=user.id,
        filename=request.filename,
        storage_path=path,
        byte_size=stored.byte_size,
    )
    log.info("document_queued", document_id=str(record.id), byte_size=stored.byte_size)

    # The fast path. The row is already durable, so if this task dies with the
    # container the pg_cron watchdog picks the document up within a minute —
    # that is the whole point of ADR 007.
    task = asyncio.create_task(state.worker.drain(max_documents=1))
    _background.add(task)
    task.add_done_callback(_background.discard)

    return ConfirmedUpload(id=record.id, status=record.status)


# asyncio holds only a weak reference to a running task, so a task nobody keeps
# can be garbage collected mid-run. This set is what keeps the fast path alive.
_background: set[asyncio.Task[int]] = set()


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete now")
async def delete_document(document_id: UUID, user: CurrentUser, state: State) -> None:
    """Delete on request, without waiting for the 24-hour timer.

    Goes through the same path as retention — storage object first, rows second
    — so "delete it now" and "it expired" cannot diverge in what they leave
    behind.
    """
    row = await state.pool.fetchrow(
        "select id from documents where id = $1 and user_id = $2 and not is_sample",
        document_id,
        user.id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such document.")

    if not await state.retention.purge_document(document_id):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "delete_failed",
                "message": "The document could not be deleted. Please try again.",
            },
        )


class Health(BaseModel):
    stages: list[str]
    kind: Literal["pipeline"] = "pipeline"


@router.get("/meta/stages", response_model=Health, summary="Pipeline stage names")
async def stages() -> Health:
    """Stage names, so the UI labels match the backend rather than duplicating it."""
    return Health(stages=list(PIPELINE_STAGES))
