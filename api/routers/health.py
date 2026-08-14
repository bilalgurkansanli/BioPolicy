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
from api.deps import embedding_model
from api.pricing import unpriced_models
from api.retrieval.floor import FLOOR_DISTANCE, FLOOR_MODEL, check_model

router = APIRouter(tags=["health"])

ProviderState = Literal["configured", "unconfigured", "ok", "error"]


class RetrievalState(BaseModel):
    """What the running process is actually doing, as opposed to what the source
    tree says it should be doing.

    Added after both of these were wrong in a live process for an afternoon with
    no way to see it from outside. A `--reload` worker had stopped reloading, so
    it served an old floor and an old rate ceiling while every fresh process —
    tests, scripts, measurements — had the new ones and agreed with each other.
    Everything looked fixed except the thing the user was talking to.

    Cheap and non-secret: three numbers and a model id, no provider call.
    """

    embedding_model: str
    floor_distance: float
    floor_measured_for: str
    # None when the provider paces itself elsewhere, e.g. the Gemini fallback.
    embed_requests_per_minute: int | None = None
    embed_tokens_per_minute: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    app_env: str
    providers: dict[str, ProviderState]
    retrieval: RetrievalState
    # Present only when something is missing, so a green response stays terse.
    missing: list[str] | None = None
    # Models this deployment calls that have no verified rate. Their spend does
    # not reach the breaker's running total, so a budget ceiling with an entry
    # here is a ceiling on part of the bill only.
    unpriced: list[str] | None = None
    # A floor calibrated in another model's vector space. Deployed, this is
    # fatal at startup; here it is the explanation for silent false refusals.
    floor_mismatch: str | None = None


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

    # Read, never built. Constructing a provider here would put a genai client
    # behind an unauthenticated route and 500 on the deployments this endpoint
    # exists to describe.
    model = embedding_model(settings)
    on_voyage = bool(settings.voyage_api_key)
    retrieval = RetrievalState(
        embedding_model=model,
        floor_distance=FLOOR_DISTANCE,
        floor_measured_for=FLOOR_MODEL,
        embed_requests_per_minute=settings.voyage_requests_per_minute if on_voyage else None,
        embed_tokens_per_minute=settings.voyage_tokens_per_minute if on_voyage else None,
    )
    mismatch = check_model(model) if settings.enable_retrieval_floor else None

    missing = settings.missing_credentials()
    unpriced = unpriced_models(settings.priced_models)
    # In development a missing credential is expected and reported, not fatal.
    # An unpriced model counts as degraded in either environment: the breaker is
    # watching a number that a real call does not move. A floor measured in
    # another model's space is the same kind of fault — a safeguard that is
    # silently deciding on the wrong scale.
    status: Literal["ok", "degraded"] = (
        "ok" if not missing and not unpriced and not mismatch else "degraded"
    )

    return HealthResponse(
        status=status,
        version=__version__,
        app_env=settings.app_env,
        providers=providers,
        retrieval=retrieval,
        # Named only where naming them helps somebody fix them.
        #
        # This route is unauthenticated, and it has to be — it is what a probe
        # and a developer with a half-configured `.env` both read. In
        # development that audience is the person who can act on the answer, so
        # the list is worth its precision.
        #
        # On a deployed environment the audience is everyone, and
        # `CREDENTIAL X IS MISSING` is a map of which capability is currently
        # unguarded. `status` still says `degraded`, the providers block still
        # says which ones are unconfigured, and the specifics stay in the logs.
        missing=([m.upper() for m in missing] or None) if not settings.is_deployed else None,
        unpriced=unpriced or None,
        floor_mismatch=mismatch,
    )


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Cheapest possible 200. For the platform's own health checking."""
    return {"status": "alive"}
