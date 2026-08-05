"""Deleting the account itself.

Every row a user owns hangs off `auth.users` with `on delete cascade`, so
removing the account removes their documents, conversations, messages and page
geometry with it — see migrations 0002, 0004 and 0008. The usage ledger is the
deliberate exception: its user reference is `on delete set null`, so what a
deleted account cost stays on the books without saying whose it was.

The deletion goes through the auth service's admin API rather than a `delete`
against `auth.users`, because that table is not this application's to write. The
auth service owns sessions, identities and refresh tokens beside it, and asking
it to remove the user is the difference between a deletion and a schema this
project happens to be able to reach.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import AsyncClient, acreate_client

from api.config import Settings
from api.logging_config import get_logger

log = get_logger(__name__)


class IdentityError(Exception):
    """The auth service could not be reached, or refused the deletion."""


class IdentityService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    async def _admin(self) -> Any:
        if self._client is None:
            if not (self._settings.supabase_url and self._settings.supabase_service_role_key):
                raise IdentityError("Auth administration is not configured.")
            self._client = await acreate_client(
                self._settings.supabase_url, self._settings.supabase_service_role_key
            )
        return self._client.auth.admin

    async def delete_user(self, user_id: UUID) -> None:
        """Remove the account. Everything keyed to it goes with it.

        A user who is already gone is not an error: the caller's intent was that
        the account should not exist, and it does not.
        """
        try:
            await (await self._admin()).delete_user(str(user_id))
        except Exception as exc:
            if "not found" in str(exc).lower():
                log.info("identity_already_deleted", user_id=str(user_id))
                return
            raise IdentityError(str(exc)) from exc

        log.info("identity_deleted", user_id=str(user_id))
