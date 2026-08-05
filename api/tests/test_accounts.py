"""The unlimited-usage allowlist.

This is the only privilege check in the codebase, so it gets the scrutiny. Each
test below is a way the check could be passed by someone who does not own the
address — the account row is consulted precisely because a token's `email` claim
is only as trustworthy as whatever produced it.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from api.accounts import AccountRepository
from api.tests.fakes import FakePool

USER = uuid4()
OWNER = "owner@example.com"


def _row(
    *,
    email: str = OWNER,
    provider: str | None = "google",
    confirmed: bool = True,
    banned: bool = False,
    deleted: bool = False,
    anonymous: bool = False,
) -> dict[str, object]:
    return {
        "id": USER,
        "email": email,
        "email_confirmed": confirmed,
        "provider": provider,
        "banned": banned,
        "deleted": deleted,
        "is_anonymous": anonymous,
    }


def _repo(
    row: dict[str, object] | None, *, allowlist: tuple[str, ...] = (OWNER,)
) -> AccountRepository:
    pool = FakePool(fetchrow=[row])
    return AccountRepository(cast(Any, pool), unlimited_emails=frozenset(allowlist))


async def test_the_allowlisted_owner_is_exempt() -> None:
    assert await _repo(_row()).is_unlimited(USER) is True


async def test_everyone_else_is_not() -> None:
    assert await _repo(_row(email="stranger@example.com")).is_unlimited(USER) is False


async def test_an_empty_allowlist_grants_nothing() -> None:
    """A deployment that forgets to configure it must not grant everyone."""
    assert await _repo(_row(), allowlist=()).is_unlimited(USER) is False


async def test_the_address_is_matched_case_insensitively() -> None:
    """Providers vary on casing; the same account must not depend on it."""
    assert await _repo(_row(email="OWNER@Example.com")).is_unlimited(USER) is True
    assert await _repo(_row(), allowlist=("OWNER@EXAMPLE.COM",)).is_unlimited(USER) is True


async def test_an_account_from_another_provider_is_refused() -> None:
    """The clause that stops a dashboard toggle becoming an escalation.

    Google is the only way in. If email/password sign-up were ever switched on,
    anyone able to type the owner's address could register it — and an address
    alone would stop being proof of anything.
    """
    assert await _repo(_row(provider="email")).is_unlimited(USER) is False
    assert await _repo(_row(provider=None)).is_unlimited(USER) is False


async def test_an_unconfirmed_address_is_refused() -> None:
    """An unconfirmed address is a claim, not a fact."""
    assert await _repo(_row(confirmed=False)).is_unlimited(USER) is False


async def test_a_banned_account_keeps_its_address_and_loses_the_exemption() -> None:
    assert await _repo(_row(banned=True)).is_unlimited(USER) is False


async def test_a_deleted_account_is_refused() -> None:
    assert await _repo(_row(deleted=True)).is_unlimited(USER) is False


async def test_an_anonymous_account_is_refused() -> None:
    assert await _repo(_row(anonymous=True)).is_unlimited(USER) is False


async def test_an_account_that_does_not_exist_is_refused() -> None:
    """A valid token for a since-deleted row must not fall through to true."""
    assert await _repo(None).is_unlimited(USER) is False


async def test_an_account_with_no_address_is_refused() -> None:
    assert await _repo(_row(email="")).is_unlimited(USER) is False


async def test_the_lookup_is_by_id_and_reads_the_ban_from_the_database_clock() -> None:
    """Two things the query has to do, neither observable through the result.

    Matching on the user id rather than the address is what makes the check a
    lookup instead of a comparison of two strings the caller supplied. Comparing
    `banned_until` against `now()` in SQL keeps a drifted server clock from
    un-banning anyone.
    """
    pool = FakePool(fetchrow=[_row()])
    await AccountRepository(cast(Any, pool), unlimited_emails=frozenset({OWNER})).is_unlimited(USER)

    query = pool.queries[0]
    assert "where id = $1" in query
    assert "banned_until > now()" in query
