"""Supabase JWT verification.

The token is verified **locally against the project's public keys**, not by
calling Supabase on every request. The project signs with ES256 and publishes a
JWKS document; asking the auth server to validate each token would add a network
round trip to the critical path of every question and make Supabase's
availability our availability.

Three checks matter and all three are easy to leave out:

* **The signature**, against the key named by the token's `kid`.
* **`aud`**, which must be `authenticated`. Without it a token for a different
  audience issued by the same project would pass.
* **`iss`**, which must be this project's auth server. Without it a validly
  signed token from *another* Supabase project is accepted, and anyone can make
  one of those in a minute.

`exp` is enforced by the library, and is the reason the frontend uses a client
that refreshes rather than holding one token forever.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status

from api.config import Settings, get_settings
from api.logging_config import get_logger

log = get_logger(__name__)

# Supabase issues every end-user token with this audience. A service-role key is
# not one of these and must never be accepted as a user.
AUDIENCE = "authenticated"

# How long a fetched signing key is reused. Long enough that key rotation is not
# a per-request cost, short enough that a rotated-out key stops working the same
# day.
JWKS_CACHE_SECONDS = 600


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    email: str | None
    is_anonymous: bool


class AuthUnavailableError(Exception):
    """Auth is not configured. Distinct from a rejected token."""


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    # Cached because the client holds the key cache. Rebuilding it per request
    # would refetch the JWKS every time and defeat the point.
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=JWKS_CACHE_SECONDS)


def _decode(token: str, *, jwks_url: str, issuer: str) -> dict[str, Any]:
    signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience=AUDIENCE,
        issuer=issuer,
        options={"require": ["exp", "sub", "aud", "iss"]},
    )


async def verify_token(token: str, settings: Settings) -> AuthenticatedUser:
    """Verify a bearer token. Raises `HTTPException(401)` if it does not hold."""
    if not settings.supabase_url:
        raise AuthUnavailableError("SUPABASE_URL is not configured")

    base = settings.supabase_url.rstrip("/")
    try:
        # PyJWKClient fetches over blocking HTTP. It is a cache hit almost
        # always, but "almost" on an event loop is still a stalled worker.
        claims = await asyncio.to_thread(
            _decode,
            token,
            jwks_url=f"{base}/auth/v1/.well-known/jwks.json",
            issuer=f"{base}/auth/v1",
        )
    except jwt.PyJWTError as exc:
        # The reason is logged, never returned: "signature verification failed"
        # versus "token is expired" is a useful distinction to an attacker and
        # to nobody else.
        log.info("token_rejected", reason=type(exc).__name__)
        raise _unauthorized() from exc

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        log.info("token_rejected", reason="sub_not_a_uuid")
        raise _unauthorized() from exc

    return AuthenticatedUser(
        id=user_id,
        email=claims.get("email") or None,
        is_anonymous=bool(claims.get("is_anonymous", False)),
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Sign in again and retry."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def optional_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser | None:
    """The signed-in user, or `None`.

    For routes that serve the public samples without an account. A *present but
    invalid* token still fails: silently downgrading a bad token to anonymous
    would hide expiry from the client, which would then look like the samples
    working and everything else mysteriously not.
    """
    token = _bearer(request)
    if token is None:
        return None
    return await verify_token(token, settings)


async def required_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    token = _bearer(request)
    if token is None:
        raise _unauthorized()
    return await verify_token(token, settings)


CurrentUser = Annotated[AuthenticatedUser, Depends(required_user)]
MaybeUser = Annotated[AuthenticatedUser | None, Depends(optional_user)]
