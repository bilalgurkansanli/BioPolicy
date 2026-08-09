"""Object storage, behind one interface.

Everything that touches the bucket goes through here for two reasons. The
smaller one is that building a Supabase client per request is wasteful. The
larger one is that the retention promise depends on deletion actually happening,
and a delete scattered across three call sites is a delete that gets skipped in
one of them.

## Files never pass through the API (constraint C1)

A 200-page policy exceeds a serverless request body limit, so the browser talks
to storage directly: it asks here for a signed URL, uploads against it, and the
API only ever sees an object path. That is why `signed_upload_url` exists and
`upload` does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from supabase import AsyncClient, acreate_client

from api.config import Settings
from api.logging_config import get_logger

log = get_logger(__name__)

# Long enough to upload 25MB on a slow connection, short enough that a leaked
# URL is not a standing write grant.
UPLOAD_URL_TTL_SECONDS = 60 * 10

# Long enough to read a policy, short enough that a leaked link expires.
VIEW_URL_TTL_SECONDS = 60 * 30


class StorageError(Exception):
    """The bucket could not be reached, or refused the operation."""


@dataclass(frozen=True, slots=True)
class SignedUpload:
    url: str
    path: str
    token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class StoredObject:
    path: str
    byte_size: int


def upload_path(user_id: UUID, document_id: UUID) -> str:
    """Where a user's upload lives.

    The user id is a path segment, which is what makes ownership checkable from
    the path alone — the confirm endpoint verifies the prefix rather than
    trusting a body field, and the storage RLS policies key off the same segment.
    The filename is deliberately absent: it is user-controlled text, and a
    document id is a name that cannot contain a traversal sequence.
    """
    return f"uploads/{user_id}/{document_id}.pdf"


class DocumentStorage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    @property
    def bucket(self) -> str:
        """The bucket name. Retention needs it to read `storage.objects`."""
        return self._settings.supabase_storage_bucket

    async def _bucket(self) -> Any:
        if self._client is None:
            if not (self._settings.supabase_url and self._settings.supabase_service_role_key):
                raise StorageError("Storage is not configured.")
            self._client = await acreate_client(
                self._settings.supabase_url, self._settings.supabase_service_role_key
            )
        return self._client.storage.from_(self._settings.supabase_storage_bucket)

    async def signed_upload_url(self, path: str) -> SignedUpload:
        try:
            result = await (await self._bucket()).create_signed_upload_url(path)
        except Exception as exc:
            raise StorageError(str(exc)) from exc

        url = result.get("signed_url") or result.get("signedUrl") or ""
        token = result.get("token") or ""
        if not url:
            raise StorageError(f"no signed url in response (keys: {sorted(result)})")
        return SignedUpload(url=url, path=path, token=token, expires_in=UPLOAD_URL_TTL_SECONDS)

    async def signed_view_url(self, path: str) -> str:
        try:
            result = await (await self._bucket()).create_signed_url(path, VIEW_URL_TTL_SECONDS)
        except Exception as exc:
            raise StorageError(str(exc)) from exc

        url = result.get("signedURL") or result.get("signedUrl") or ""
        if not url:
            raise StorageError(f"no signed url in response (keys: {sorted(result)})")
        return url

    async def stat(self, path: str) -> StoredObject | None:
        """What is actually in the bucket at `path`, or `None`.

        The confirm endpoint calls this rather than believing the client's
        reported size. A row created for an object that was never uploaded
        becomes a queue entry that fails on every attempt.
        """
        try:
            info = await (await self._bucket()).info(path)
        except Exception:
            return None

        size = info.get("size") if isinstance(info, dict) else getattr(info, "size", None)
        if size is None:
            return None
        return StoredObject(path=path, byte_size=int(size))

    async def download(self, path: str) -> bytes:
        try:
            return bytes(await (await self._bucket()).download(path))
        except Exception as exc:
            raise StorageError(str(exc)) from exc

    async def remove(self, path: str) -> bool:
        """Delete one object. Returns whether it is now gone.

        An object that was already absent counts as gone. Retention re-runs, and
        a purge that reports failure because the file was deleted last time
        would keep the row alive forever.
        """
        try:
            await (await self._bucket()).remove([path])
        except Exception as exc:
            log.error("storage_remove_failed", path=path, error=str(exc))
            return await self.stat(path) is None
        return True
