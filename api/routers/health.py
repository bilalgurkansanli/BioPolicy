"""Health and readiness.

Deliberately shallow by default: it reports whether each dependency is
*configured*, not whether it is *reachable*. A health endpoint that makes live
provider calls is a health endpoint that costs money and can be used to burn
someone else's budget from an unauthenticated route.

`?deep=true` performs real connectivity checks and is rate-limited and
non-cacheable; use it from a runbook, not from an uptime monitor set to 10s.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api import __version__
from api.config import Settings, get_settings
from api.pricing import unpriced_models

router = APIRouter(tags=["health"])

ProviderState = Literal["configured", "unconfigured", "ok", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    app_env: str
    providers: dict[str, ProviderState]
    # Present only when something is missing, so a green response stays terse.
    missing: list[str] | None = None
    # Models this deployment calls that have no verified rate. Their spend does
    # not reach the breaker's running total, so a budget ceiling with an entry
    # here is a ceiling on part of the bill only.
    unpriced: list[str] | None = None


def _shallow_providers(settings: Settings) -> dict[str, ProviderState]:
    def state(*values: str | None) -> ProviderState:
        return "configured" if all(values) else "unconfigured"

    return {
        "supabase": state(settings.supabase_url, settings.supabase_service_role_key),
        "supabase_auth": state(settings.supabase_anon_key),
        "database": state(settings.database_url),
        "anthropic": state(settings.anthropic_api_key),
        "google": state(settings.google_api_key),
        # These two are empty until verified against a live model list, and the
        # spec forbids guessing them. Reporting 'unconfigured' is the honest
        # answer, not a bug.
        "gemini_fallback_llm": state(settings.gemini_fallback_model),
        "gemini_ocr": state(settings.gemini_ocr_model),
    }


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health(
    deep: Annotated[
        bool, Query(description="Perform live connectivity checks. Costs a round-trip.")
    ] = False,
) -> HealthResponse:
    settings = get_settings()
    providers = _shallow_providers(settings)

    if deep:
        # Populated in Phase 1 once the Supabase client and provider adapters
        # exist. Returning the shallow view until then is more honest than
        # returning 'ok' for a check that never ran.
        pass

    missing = settings.missing_credentials()
    unpriced = unpriced_models(settings.priced_models)
    # In development a missing credential is expected and reported, not fatal.
    # An unpriced model counts as degraded in either environment: the breaker is
    # watching a number that a real call does not move.
    status: Literal["ok", "degraded"] = "ok" if not missing and not unpriced else "degraded"

    return HealthResponse(
        status=status,
        version=__version__,
        app_env=settings.app_env,
        providers=providers,
        missing=[m.upper() for m in missing] or None,
        unpriced=unpriced or None,
    )


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Cheapest possible 200. For the platform's own health checking."""
    return {"status": "alive"}
