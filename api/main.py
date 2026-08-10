"""FastAPI application factory.

Two behaviours here are load-bearing rather than boilerplate:

* **Unhandled exceptions never reach the client.** They become a generic 500
  carrying a request id. The real error, with its traceback, goes to the server
  log under that same id. Section 5 of the spec requires user-safe failures; a
  stack trace in a JSON response leaks file paths, library versions and
  occasionally credentials.

* **Every response carries `X-Request-ID`.** When a user reports "it said it
  couldn't find the answer", that id is the only way to find the corresponding
  retrieval trace without logging their question.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api import __version__
from api.config import get_settings
from api.db import create_pool
from api.deps import AppState, embedding_model
from api.logging_config import configure_logging, get_logger
from api.pricing import unpriced_models
from api.retrieval.floor import check_model
from api.routers import (
    account,
    chat,
    conversations,
    documents,
    health,
    internal,
    stats,
)

log = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# A UUID is 36 characters; this leaves room for a tracing format without leaving
# room for a caller to put a kilobyte on every log line the request produces.
MAX_REQUEST_ID_CHARS = 64
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]+")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_deployed)

    # The pool and the providers are built once. A failure here must not take
    # the whole process down: `/api/health` is the route whose job is to explain
    # what is broken, and it cannot do that if a database outage prevents boot.
    pool = None
    if settings.database_url:
        try:
            pool = await create_pool()
            app.state.app_state = AppState.build(pool, settings)
        # Degrade, do not fail to start.
        except Exception as exc:
            log.error("startup_database_unavailable", error=str(exc))
            app.state.app_state = None
    else:
        app.state.app_state = None

    # A model without a rate is not a smaller bill, it is a bill the breaker
    # cannot see. Deployed, that is the same class of fault as a missing
    # credential and gets the same treatment: refuse to start and say which.
    unpriced = unpriced_models(settings.priced_models)
    if unpriced and settings.is_deployed:
        raise RuntimeError(
            f"APP_ENV={settings.app_env} but these models have no verified rate: "
            f"{', '.join(unpriced)}. Their spend would never reach the circuit "
            "breaker's total, so GLOBAL_BUDGET_USD would cap part of the bill only. "
            "Set MODEL_PRICES and MODEL_PRICES_VERIFIED_ON — see .env.example."
        )

    # The same rule, for the same reason, applied to the other number that is
    # only meaningful against a specific model. An unpriced model spends money
    # the breaker cannot see; a floor measured in another vector space refuses
    # questions nobody can see being refused.
    floor_complaint = check_model(embedding_model(settings))
    if floor_complaint and settings.enable_retrieval_floor:
        if settings.is_deployed:
            raise RuntimeError(f"APP_ENV={settings.app_env} but {floor_complaint}")
        log.warning("retrieval_floor_model_mismatch", detail=floor_complaint)

    missing = settings.missing_credentials()
    log.info(
        "startup",
        version=__version__,
        app_env=settings.app_env,
        # Surfaced at boot so a misconfigured deployment is obvious in the first
        # log line rather than in the first user-visible failure.
        unconfigured=[m.upper() for m in missing] or None,
        citation_binding=settings.enable_citation_binding,
        self_verification=settings.enable_self_verification,
        unpriced=unpriced or None,
    )
    if missing and not settings.is_deployed:
        log.warning(
            "running_with_unconfigured_providers",
            detail="Development mode. Endpoints depending on these will return 503.",
        )

    yield

    if pool is not None:
        await pool.close()
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="BioPolicy API",
        description=(
            "Citation-grounded question answering over insurance policies and legal "
            "contracts. Every answer is either bound to verifiable spans of the source "
            "document, or refused."
        ),
        version=__version__,
        lifespan=lifespan,
        # No interactive docs in production: the schema describes internal
        # endpoints and rate-limit shapes that are not worth publishing.
        docs_url=None if settings.app_env == "production" else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.app_env == "production" else "/api/openapi.json",
    )

    if settings.cors_allow_origins:
        # Normally empty: the browser reaches the API same-origin via a Next.js
        # rewrite, so no preflight happens at all. Populated only for split-origin
        # local development.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        )

    if settings.app_env == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["biopolicy.bilalgurkansanli.com", "*.vercel.app"],
        )

    def _request_id(supplied: str | None) -> str:
        """Honour a caller's correlation id, within limits.

        Accepting the header is deliberate — it lets a trace span the frontend
        and this service — but the value is unauthenticated input that ends up
        in every log line for the request and in a response header, so it is
        bounded and restricted to characters that cannot be mistaken for
        structure. Anything else gets a fresh id rather than a rejection: a bad
        correlation id is not worth failing a request over.
        """
        if (
            supplied
            and len(supplied) <= MAX_REQUEST_ID_CHARS
            and _SAFE_REQUEST_ID.fullmatch(supplied)
        ):
            return supplied
        return str(uuid.uuid4())

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]
    ) -> JSONResponse:
        request_id = _request_id(request.headers.get(REQUEST_ID_HEADER))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        # exc_info carries the traceback into the server log only.
        log.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side. Nothing was charged.",
                    "request_id": request_id,
                }
            },
            headers={REQUEST_ID_HEADER: request_id},
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(internal.router, prefix="/api")
    app.include_router(account.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")

    return app


app = create_app()
