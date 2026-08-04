"""Document listing, status, and signed viewing URLs.

Sample documents are readable without authentication — the public demo has to
work before anyone signs in. Everything else is owner-scoped, and the scoping is
done in SQL rather than left to RLS, because the API holds a service-role key
and bypasses every policy (see `api/retrieval/store.py`).

The upload path is deliberately absent from this file for now: it needs auth,
and until it exists there is no way to create a non-sample document. Adding a
half-built upload route would be worse than not having one — it would look
available.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from supabase import acreate_client

from api.constants import PIPELINE_STAGES
from api.deps import Config, State
from api.logging_config import get_logger

router = APIRouter(prefix="/documents", tags=["documents"])
log = get_logger(__name__)

# How long a viewing URL stays valid. Long enough to read a policy, short enough
# that a leaked link is not a permanent one.
SIGNED_URL_TTL_SECONDS = 60 * 30


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


@router.get("/samples", response_model=list[DocumentSummary], summary="Bundled samples")
async def samples(state: State) -> list[DocumentSummary]:
    """The three documents the demo serves without an upload or an account."""
    rows = await state.pool.fetch(
        "select id, filename, page_count, source_type, detected_lang, status, is_sample "
        "from documents where is_sample and status = 'ready' order by filename"
    )
    return [DocumentSummary(**dict(row)) for row in rows]


@router.get("/{document_id}", response_model=DocumentStatus, summary="Ingestion status")
async def document_status(document_id: UUID, state: State) -> DocumentStatus:
    row = await state.pool.fetchrow(
        """
        select d.id, d.status, d.page_count, d.source_type, d.detected_lang,
               d.error_message, d.is_sample,
               (select count(*) from chunks c where c.document_id = d.id) as chunk_count
          from documents d
         where d.id = $1 and d.is_sample
        """,
        document_id,
    )
    if row is None:
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
async def viewing_url(document_id: UUID, state: State, settings: Config) -> SignedUrl:
    """A short-lived link the PDF viewer can fetch.

    The bucket is private, so the browser cannot read the object directly — and
    that is the point. A public bucket would leave every uploaded policy
    readable by URL while RLS carefully guarded the metadata around it.
    """
    row = await state.pool.fetchrow(
        "select storage_path from documents where id = $1 and is_sample", document_id
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such document.")

    client = await acreate_client(
        settings.supabase_url or "", settings.supabase_service_role_key or ""
    )
    signed = await client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
        row["storage_path"], SIGNED_URL_TTL_SECONDS
    )
    url = signed.get("signedURL") or signed.get("signedUrl") or ""
    if not url:
        log.error("signed_url_missing", document_id=str(document_id), keys=sorted(signed))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Could not produce a viewing link.")
    return SignedUrl(url=url, expires_in=SIGNED_URL_TTL_SECONDS)


class Health(BaseModel):
    stages: list[str]
    kind: Literal["pipeline"] = "pipeline"


@router.get("/meta/stages", response_model=Health, summary="Pipeline stage names")
async def stages() -> Health:
    """Stage names, so the UI labels match the backend rather than duplicating it."""
    return Health(stages=list(PIPELINE_STAGES))
