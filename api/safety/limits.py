"""The exceptions the safety layer raises, and how they reach the client.

Separate from the guards themselves so a route can catch them without importing
a database-bound object, and so the HTTP mapping lives in exactly one place. A
quota message that differs between two endpoints is a message the frontend
cannot translate.
"""

from __future__ import annotations

from fastapi import HTTPException, status


class LimitExceededError(Exception):
    """Base class. Carries a machine-readable code and a retry hint."""

    code = "limit_exceeded"

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds

    def as_http(self) -> HTTPException:
        headers = {}
        if self.retry_after_seconds is not None:
            headers["Retry-After"] = str(self.retry_after_seconds)
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": self.code, "message": self.message},
            headers=headers or None,
        )


class DailyQuotaExceededError(LimitExceededError):
    code = "daily_quota_exceeded"


class BudgetExhaustedError(LimitExceededError):
    """The global budget is spent. Nobody gets served, not just this user.

    Deliberately a different code from a quota: "come back tomorrow" is wrong
    advice here, and telling a visitor to wait for something that will not
    happen is worse than telling them the demo is off.
    """

    code = "budget_exhausted"

    def as_http(self) -> HTTPException:
        # 503, not 429: this is not the caller's rate, and no amount of retrying
        # will help. A 429 invites exactly the retry loop that must not happen.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": self.code, "message": self.message},
        )
