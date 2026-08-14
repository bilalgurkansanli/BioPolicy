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
import json
from collections.abc import Coroutine, Mapping
from typing import Any, Literal
from uuid import UUID, uuid4

from asyncpg.exceptions import UniqueViolationError
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import AuthenticatedUser, CurrentUser, MaybeUser
from api.constants import PIPELINE_STAGES
from api.deps import Config, State
from api.generation.profile import PROFILE_MAX_CHUNKS, PolicyProfile
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


class InjectionFinding(BaseModel):
    rule: str
    why: str
    excerpt: str


class DocumentSummary(BaseModel):
    id: UUID
    filename: str
    page_count: int | None
    source_type: str | None
    detected_lang: str | None
    status: str
    is_sample: bool
    injection_findings: list[InjectionFinding] | None = None
    """Instruction-shaped text found at ingest.

    `null` and `[]` are different answers and both are sent. `null` means the
    document predates the scan; `[]` means it was scanned and nothing was found.
    Collapsing them would let the interface show a clean bill of health for a
    document nobody ever checked.
    """


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
    injection_findings: list[InjectionFinding] | None = None


class SignedUrl(BaseModel):
    url: str
    expires_in: int


def _findings(raw: object) -> list[InjectionFinding] | None:
    """asyncpg hands back jsonb as a string; null stays null.

    Kept out of the models so the two read paths cannot disagree about what a
    missing value means.
    """
    if raw is None:
        return None
    items: list[dict[str, str]] = json.loads(raw) if isinstance(raw, str) else raw  # type: ignore[assignment]
    return [InjectionFinding(**item) for item in items]


def _summary(row: Mapping[str, object]) -> DocumentSummary:
    data = dict(row)
    data["injection_findings"] = _findings(data.get("injection_findings"))
    return DocumentSummary(**data)


# -----------------------------------------------------------------------------
# reading
# -----------------------------------------------------------------------------


@router.get("/samples", response_model=list[DocumentSummary], summary="Bundled samples")
async def samples(state: State) -> list[DocumentSummary]:
    """The three documents the demo serves without an upload or an account."""
    rows = await state.pool.fetch(
        "select id, filename, page_count, source_type, detected_lang, status, is_sample, "
        "injection_findings "
        "from documents where is_sample and status = 'ready' order by filename"
    )
    return [_summary(row) for row in rows]


@router.get("/mine", response_model=list[DocumentSummary], summary="Your own documents")
async def mine(user: CurrentUser, state: State) -> list[DocumentSummary]:
    rows = await state.pool.fetch(
        "select id, filename, page_count, source_type, detected_lang, status, is_sample, "
        "injection_findings "
        "from documents where user_id = $1 and not is_sample order by created_at desc",
        user.id,
    )
    return [_summary(row) for row in rows]


@router.get("/{document_id}", response_model=DocumentStatus, summary="Ingestion status")
async def document_status(document_id: UUID, state: State, user: MaybeUser) -> DocumentStatus:
    row = await state.pool.fetchrow(
        """
        select d.id, d.status, d.page_count, d.source_type, d.detected_lang,
               d.error_message, d.is_sample, d.injection_findings,
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
        injection_findings=_findings(row["injection_findings"]),
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

    try:
        record = await state.documents.create(
            document_id=request.document_id,
            user_id=user.id,
            filename=request.filename,
            storage_path=path,
            byte_size=stored.byte_size,
        )
    except UniqueViolationError as exc:
        # The id is the client's to send — it names the object it just uploaded
        # — so a confirm can arrive twice, or name a row that already exists.
        # `create` is a plain INSERT rather than an upsert, which is what stops
        # this from being a way to overwrite somebody's document; without this
        # branch it was simply a 500.
        #
        # The message does not say whether the id exists. It cannot be guessed
        # in practice, but an endpoint that answers "taken" or "free" about an
        # identifier is an enumeration oracle, and there is no reason to build
        # one here.
        log.info("confirm_duplicate_id", document_id=str(request.document_id))
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "already_confirmed",
                "message": "That upload has already been confirmed. Please start a new one.",
            },
        ) from exc
    log.info("document_queued", document_id=str(record.id), byte_size=stored.byte_size)

    # The fast path. The row is already durable, so if this task dies with the
    # container the pg_cron watchdog picks the document up within a minute —
    # that is the whole point of ADR 007.
    _spawn(state.worker.drain(max_documents=1))

    return ConfirmedUpload(id=record.id, status=record.status)


# asyncio holds only a weak reference to a running task, so a task nobody keeps
# can be garbage collected mid-run. This set is what keeps such a task alive:
# the ingestion fast path above, and the profile sweep below, which must finish
# recording what it spent even if the caller has gone.
_background: set[asyncio.Task[Any]] = set()


def _spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


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


class PageLine(BaseModel):
    text: str
    bbox: dict[str, float]


class PageLines(BaseModel):
    page: int
    lines: list[PageLine]


@router.get(
    "/{document_id}/pages/{page}/lines",
    response_model=PageLines,
    summary="Line geometry for an OCR'd page",
)
async def page_lines(document_id: UUID, page: int, user: MaybeUser, state: State) -> PageLines:
    """Where each transcribed line sits, for one page.

    Only OCR'd pages have any. A page with a text layer returns an empty list,
    and the viewer is expected to search the text layer itself rather than ask
    here — the answer would be the same and the round trip would be wasted.

    Fetched on demand, per page, when a citation is clicked: a thirty-page scan
    runs to well over a thousand lines, and almost none of them are ever needed.
    """
    row = await state.pool.fetchrow(
        "select id from documents where id = $1 and (is_sample or user_id = $2)",
        document_id,
        user.id if user else None,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such document.")

    lines = await state.store.page_lines(document_id, page)
    return PageLines(page=page, lines=[PageLine(text=text, bbox=bbox) for text, bbox in lines])


# -----------------------------------------------------------------------------
# typed extraction
# -----------------------------------------------------------------------------
#
# Two verbs, deliberately. GET reads the cache and never spends anything, so the
# workspace can ask on every document open. POST is the one that calls a model,
# and it is the one that needs an account and a quota check.
#
# Folding both into GET would make opening a document a billable event, and a
# refresh loop in somebody's browser an expensive one.


async def _profile_owner(document_id: UUID, user: object, state: State) -> UUID:
    """Check the caller may see this document, and return whose it is.

    The owner id, not the caller's: a sample belongs to the seeder and is
    readable by everyone, so scoping the chunk sweep to the *caller* would
    return nothing for the documents the demo is built on.

    404 rather than 403 for someone else's document, matching the rest of this
    router — whether an id exists is not something a stranger should be able to
    probe.
    """
    row = await state.pool.fetchrow(
        "select user_id from documents "
        "where id = $1 and (is_sample or user_id = $2) and status = 'ready'",
        document_id,
        getattr(user, "id", None),
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No such document, or it is not ready yet."
        )
    return UUID(str(row["user_id"]))


@router.get(
    "/{document_id}/profile",
    response_model=PolicyProfile | None,
    summary="Cached typed extraction",
)
async def read_profile(document_id: UUID, user: MaybeUser, state: State) -> PolicyProfile | None:
    """The document read into the fixed schema, if it has been read.

    `null` means nobody has run the extraction yet — distinct from a profile
    whose `entries` are empty, which means it ran and the document filled no
    slots. The interface renders those two states differently, so this route
    must not collapse them into one.
    """
    await _profile_owner(document_id, user, state)
    cached = await state.documents.get_profile(document_id)
    return PolicyProfile.model_validate(cached) if cached else None


@router.post(
    "/{document_id}/profile",
    response_model=PolicyProfile,
    summary="Run typed extraction",
)
async def build_profile(document_id: UUID, user: CurrentUser, state: State) -> PolicyProfile:
    """Sweep the whole document into the schema, then cache it.

    Returns the cache when there is one, without spending anything. That is what
    keeps the sample documents affordable: the first signed-in visitor pays for
    the extraction and everyone after them reads the result.

    **Costs one question from the daily allowance**, and should: a sweep is
    several provider calls where an answer is two. `ensure_can_ask` reserves the
    slot up front, and `refund_question` hands it back when the sweep produced
    nothing worth keeping — the same contract the answering route follows.
    """
    owner = await _profile_owner(document_id, user, state)

    cached = await state.documents.get_profile(document_id)
    if cached:
        return PolicyProfile.model_validate(cached)

    try:
        # Breaker before quota, as in `chat`: when the demo is out of money,
        # telling a visitor they have allowance left would be a lie.
        await state.breaker.ensure_capacity()
        await state.quota.ensure_can_ask(user.id)
    except LimitExceededError as exc:
        raise exc.as_http() from exc

    # Run as a task, and await that task rather than doing the work inline.
    #
    # This route spends money and then records it, and the recording must not
    # depend on the caller still being there — the same failure the answering
    # stream had, and worth pre-empting here rather than discovering it. A task
    # is not cancelled when the request that started it is, so a browser that
    # navigates away mid-sweep still leaves a ledger entry, a fed breaker and a
    # cached profile nobody has to pay for twice.
    #
    # The lock lives inside the task for the same reason: held by the handler it
    # would be released the moment the handler was cancelled, while the sweep it
    # was guarding carried on.
    profile: PolicyProfile = await _spawn(_extract_profile(document_id, owner, user, state))
    return profile


async def _extract_profile(
    document_id: UUID, owner: UUID, user: AuthenticatedUser, state: State
) -> PolicyProfile:
    """The sweep itself, and everything that has to happen because of it."""
    # One extraction per document at a time. Two browsers opening the same
    # uncached sample together would otherwise both pay for it. Process-local,
    # so it does not help across instances — the waste it prevents is the common
    # case, and the cache makes the uncommon one self-correcting.
    #
    # The lock is never removed from the map. Deleting it on the way out looks
    # tidier and is wrong: a waiter already holding a reference would keep using
    # an entry no longer in the map, and the next arrival would create a second
    # lock and run alongside it. An empty `asyncio.Lock` per document seen is a
    # smaller cost than the bug.
    async with _profile_locks.setdefault(document_id, asyncio.Lock()):
        cached = await state.documents.get_profile(document_id)
        if cached:
            # Somebody else did the work while this request waited on the lock,
            # so the slot reserved for it was never spent.
            await state.quota.refund_question(user.id)
            return PolicyProfile.model_validate(cached)

        chunks = await state.store.all_chunks(
            document_id=document_id,
            user_id=owner,
            limit=PROFILE_MAX_CHUNKS,
        )
        total = await state.store.chunk_count(document_id)

        outcome = await state.profiler.extract(chunks)
        # `chunks_total` from the store, not from what the sweep read: the
        # profile's own coverage figure has to come from the document's real
        # size or "complete" means nothing.
        profile = outcome.profile.model_copy(update={"chunks_total": total})

        if outcome.usage:
            cost = await state.usage.record(user_id=user.id, records=outcome.usage)
            state.breaker.note_spend(cost)

        # An extraction where every batch failed is a provider outage, not a
        # reading of the document. Caching it would make the outage permanent
        # for this document until somebody cleared the column by hand.
        if profile.entries or profile.batches_failed == 0:
            await state.documents.set_profile(document_id, profile.model_dump(mode="json"))
        else:
            log.warning(
                "profile_not_cached",
                document_id=str(document_id),
                batches_failed=profile.batches_failed,
            )
            # Nothing usable came back, so the day's allowance should not have
            # paid for it. The provider calls that did land are still in the
            # ledger above — the refund is of the *slot*, not of the money.
            await state.quota.refund_question(user.id)

    return profile


_profile_locks: dict[UUID, asyncio.Lock] = {}


class Capabilities(BaseModel):
    stages: list[str]
    max_upload_bytes: int
    retention_hours: int
    kind: Literal["pipeline"] = "pipeline"


@router.get("/meta/stages", response_model=Capabilities, summary="Limits and stage names")
async def capabilities(settings: Config) -> Capabilities:
    """What the interface would otherwise have to hard-code.

    The upload screen prints the size limit and the retention window, and both
    are promises. A copy of them in the frontend is a copy that drifts, and the
    first symptom is a screen confidently stating a limit the API does not
    enforce.
    """
    return Capabilities(
        stages=list(PIPELINE_STAGES),
        max_upload_bytes=settings.max_upload_bytes,
        retention_hours=settings.retention_hours,
    )
