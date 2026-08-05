"""Who you are and what you have left today.

One route, and the interface leans on it heavily: it is what lets the composer
disable itself at zero rather than accepting a fourth question and refusing it
after the fact.

That makes it a *display* of the limit and never the limit itself. Every path
that spends money re-checks (`api/safety/quota.py`), because a client that lies
about what it was told here must not be able to buy anything with the lie.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.auth import CurrentUser
from api.deps import State
from api.identity import IdentityError
from api.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/me", tags=["account"])


class Allowance(BaseModel):
    unlimited: bool
    questions_used: int
    questions_limit: int
    questions_left: int | None
    """`null` when unlimited. Distinct from zero, and never rendered as one."""

    documents_used: int
    documents_limit: int
    documents_left: int | None


class Me(BaseModel):
    id: str
    email: str | None
    allowance: Allowance


@router.get("", response_model=Me, summary="The signed-in account")
async def me(user: CurrentUser, state: State) -> Me:
    allowance = await state.quota.allowance(user.id)
    account = await state.accounts.get(user.id)
    return Me(
        id=str(user.id),
        # From the account row rather than the token, so what is shown is what
        # the allowlist is matched against — one source, no chance of the
        # interface displaying an address the limits did not use.
        email=account.email if account else None,
        allowance=Allowance(
            unlimited=allowance.unlimited,
            questions_used=allowance.questions_used,
            questions_limit=allowance.questions_limit,
            questions_left=allowance.questions_left,
            documents_used=allowance.documents_used,
            documents_limit=allowance.documents_limit,
            documents_left=allowance.documents_left,
        ),
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete this account and everything in it",
)
async def delete_me(user: CurrentUser, state: State) -> None:
    """Erase the account on its owner's request.

    Files first, account second, and the second only if the first succeeded.
    Every row a user owns cascades from `auth.users`, but nothing in the bucket
    does: an account deleted while one of its PDFs was still in storage would
    leave that file with no row pointing at it, no owner to ask for it and no
    expiry to catch it. So a bucket that refuses a delete stops the whole
    operation, and the account is still there to try again with.
    """
    if not await state.retention.purge_user_documents(user.id):
        log.error("account_delete_storage_failed", user_id=str(user.id))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "delete_failed",
                "message": "Your documents could not be deleted, so the account was kept. Please try again.",
            },
        )

    try:
        await state.identity.delete_user(user.id)
    except IdentityError as exc:
        log.error("account_delete_failed", user_id=str(user.id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "delete_failed",
                "message": "The account could not be deleted. Please try again.",
            },
        ) from exc

    log.info("account_deleted", user_id=str(user.id))
