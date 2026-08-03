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
from api.logging_config import configure_logging, get_logger
from api.routers import health

log = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_deployed)

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
    )
    if missing and not settings.is_deployed:
        log.warning(
            "running_with_unconfigured_providers",
            detail="Development mode. Endpoints depending on these will return 503.",
        )

    yield

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

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]
    ) -> JSONResponse:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
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

    return app


app = create_app()
