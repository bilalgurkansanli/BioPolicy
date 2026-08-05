"""Endpoints called by the database, not by people.

pg_cron cannot delete a storage object — only the Storage API owns the bucket
backend — so the retention job calls back into this service instead of running a
`DELETE` (migration 0007 explains that at length). The queue watchdog works the
same way.

These are guarded by a shared secret in `X-Job-Secret` rather than by a user
token: the caller is Postgres, which has no session. The secret lives in
`app_settings` so rotating it is an `UPDATE` rather than a migration.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from api.deps import Config, State
from api.logging_config import get_logger

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)
log = get_logger(__name__)


def _authorize(settings_secret: str | None, provided: str | None) -> None:
    if not settings_secret:
        # Refusing rather than allowing: an unset secret must not turn these
        # into open endpoints. The scheduled jobs already tolerate doing
        # nothing until the project is configured.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "not_configured", "message": "No job secret is configured."},
        )
    # Constant-time: these endpoints delete data and cost money, and a timing
    # oracle on a fixed secret is worth the one-line defence.
    if provided is None or not hmac.compare_digest(provided, settings_secret):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Bad job secret."},
        )


class PurgeResult(BaseModel):
    purged: int
    chunks_deleted: int
    failed: int


@router.post("/purge", response_model=PurgeResult, summary="Delete expired documents")
async def purge(
    state: State,
    settings: Config,
    x_job_secret: str | None = Header(default=None),
) -> PurgeResult:
    _authorize(settings.purge_job_secret, x_job_secret)
    report = await state.retention.purge_expired()
    return PurgeResult(**report.as_dict)


class SweepResult(BaseModel):
    processed: int


@router.post("/process-queue", response_model=SweepResult, summary="Ingestion watchdog")
async def process_queue(
    state: State,
    settings: Config,
    x_job_secret: str | None = Header(default=None),
) -> SweepResult:
    _authorize(settings.purge_job_secret, x_job_secret)
    processed = await state.worker.drain()
    return SweepResult(processed=processed)
