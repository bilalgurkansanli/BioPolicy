"""Who the caller is, according to the database rather than their token.

## Why not read the email out of the JWT

The token carries one. It is signed, so it has not been tampered with, and for
almost everything that is enough — `AuthenticatedUser.id` comes straight from
`sub` and no lookup would improve it.

It is not enough for *privilege*. The unlimited-usage allowlist is matched on an
email address, and an address in a token is only as trustworthy as the path that
put it there: a project with a second auth provider enabled, or email/password
sign-up left on, mints a valid token for anyone who can type the address. The
account row knows what actually happened — which provider it came from, whether
the address was ever confirmed, whether the account has since been banned or
deleted — and that is what the check reads.

The cost is one indexed lookup per privileged decision. That is the right price.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from api.logging_config import get_logger

log = get_logger(__name__)

# The only provider this project signs anyone in with. An account that arrived
# any other way is not one Google vouched for, whatever its address says.
REQUIRED_PROVIDER = "google"


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    email: str | None
    provider: str | None
    email_confirmed: bool
    usable: bool
    """False when the account is banned, deleted, or anonymous."""


class AccountRepository:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        unlimited_emails: frozenset[str],
        subject_pepper: str | None = None,
    ) -> None:
        self._pool = pool
        # Lower-cased once, here, so no call site has to remember to.
        self._unlimited = frozenset(email.strip().lower() for email in unlimited_emails if email)
        self._pepper = (subject_pepper or "").encode("utf-8") or None

    async def get(self, user_id: UUID) -> Account | None:
        row = await self._pool.fetchrow(
            """
            select id,
                   email,
                   email_confirmed_at is not null as email_confirmed,
                   raw_app_meta_data ->> 'provider' as provider,
                   -- Compared against the database's clock rather than this
                   -- process's: a server whose time has drifted must not be
                   -- able to un-ban an account.
                   (banned_until is not null and banned_until > now()) as banned,
                   deleted_at is not null as deleted,
                   is_anonymous
              from auth.users
             where id = $1
            """,
            user_id,
        )
        if row is None:
            return None

        return Account(
            id=row["id"],
            email=(row["email"] or "").strip().lower() or None,
            provider=row["provider"],
            email_confirmed=bool(row["email_confirmed"]),
            usable=not (row["banned"] or row["deleted"] or row["is_anonymous"]),
        )

    async def subject(self, user_id: UUID) -> str | None:
        """The pseudonymous key this account's daily allowance is counted under.

        ## Why the allowance cannot be counted per account

        Deleting an account and signing in again produces a *new* `auth.users`
        row with a new id. `usage_events.user_id` becomes null and `documents`
        cascades away, so both counters read zero and the daily limit is fresh —
        an unlimited allowance for anybody willing to click twice. Deleting the
        account is a right this project intends to keep offering, so the limit
        has to survive it instead.

        ## What is stable across that, and what is not

        Google's `sub`. It identifies the Google account rather than the row
        Supabase made for it, it is stable for the life of that account, and it
        is not reused. It arrives in `auth.identities.provider_id`, which is the
        provider's own value rather than anything this application derived.

        The email address would also be stable-ish, and is the wrong choice: it
        is personal data, addresses change, and storing one keyed to "has spent
        their allowance" is a record about a person rather than a counter.

        Returned as an HMAC rather than the `sub` itself. The counter's whole
        job is to recognise a repeat, which a keyed digest does exactly as well
        while being useless to anyone reading the table — including to us,
        without the pepper.

        `None` has one meaning and it is not "no limit": either the deployment
        has no pepper configured, or this account has no Google identity. Both
        send the caller back to the per-account count, which is the behaviour
        that existed before this method and still binds; it simply does not
        survive a deletion. `/api/health` reports a missing pepper, and a
        deployed environment refuses to boot without one.
        """
        if self._pepper is None:
            return None

        row = await self._pool.fetchrow(
            """
            select provider_id from auth.identities
             where user_id = $1 and provider = $2
             limit 1
            """,
            user_id,
            REQUIRED_PROVIDER,
        )
        if row is None or not row["provider_id"]:
            return None

        return hmac.new(
            self._pepper, str(row["provider_id"]).encode("utf-8"), hashlib.sha256
        ).hexdigest()

    async def is_unlimited(self, user_id: UUID) -> bool:
        """Whether this account is exempt from the daily limits.

        Every clause below is a way the check could otherwise be passed by
        someone who is not the owner of the address:

        * **The allowlist may be empty.** Then nobody is exempt, and no lookup
          happens at all. A misconfigured deployment grants nothing.
        * **The account must be usable.** A banned or deleted account keeps its
          row, and its address with it.
        * **The address must be confirmed.** An unconfirmed address is a claim,
          not a fact.
        * **It must have come from Google.** If a second provider is ever
          switched on in the dashboard, an address alone stops being proof of
          anything — this is the clause that keeps that from silently becoming a
          privilege escalation.
        """
        if not self._unlimited:
            return False

        account = await self.get(user_id)
        if account is None or not account.usable:
            return False
        if not account.email or not account.email_confirmed:
            return False
        if account.provider != REQUIRED_PROVIDER:
            log.warning(
                "unlimited_denied_wrong_provider",
                user_id=str(user_id),
                provider=account.provider,
            )
            return False

        return account.email in self._unlimited
