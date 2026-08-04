"""Shared application state and FastAPI dependencies.

Providers are constructed once at startup rather than per request. On a
scale-to-zero platform the first request already pays a cold start; building an
HTTP client and a connection pool on top of that, for every request, turns a
slow first impression into a slow every-impression.

Nothing here reaches for a credential at import time. A missing key surfaces as
a 503 naming the capability, not as an exception during module load — which on a
serverless platform means the whole function fails to boot and every route
returns an opaque error, including `/api/health`, the one route whose job is to
explain what is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from api.config import Settings, get_settings
from api.documents import DocumentRepository
from api.generation.answerer import Answerer
from api.generation.llm import FailoverLLM, LLMProvider
from api.generation.providers import AnthropicLLM, GeminiLLM
from api.generation.schemas import ANSWER_JSON_SCHEMA, VERIFICATION_JSON_SCHEMA
from api.generation.verifier import Verifier
from api.logging_config import get_logger
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import ChunkStore

log = get_logger(__name__)


@dataclass(slots=True)
class AppState:
    """Everything built once at startup and shared across requests."""

    pool: asyncpg.Pool
    documents: DocumentRepository
    store: ChunkStore
    retriever: HybridRetriever
    answerer: Answerer

    @classmethod
    def build(cls, pool: asyncpg.Pool, settings: Settings) -> AppState:
        embedder = GeminiEmbedder(settings.google_api_key or "", settings.gemini_embedding_model)
        store = ChunkStore(pool)

        answering: list[LLMProvider] = [
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=ANSWER_JSON_SCHEMA,
            )
        ]
        if settings.google_api_key and settings.gemini_fallback_model:
            answering.append(
                GeminiLLM(
                    settings.google_api_key,
                    settings.gemini_fallback_model,
                    json_schema=ANSWER_JSON_SCHEMA,
                )
            )

        rewriter = (
            GeminiLLM(settings.google_api_key, settings.gemini_fallback_model)
            if settings.google_api_key and settings.gemini_fallback_model
            else None
        )

        verifier = Verifier(
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=VERIFICATION_JSON_SCHEMA,
            )
        )

        return cls(
            pool=pool,
            documents=DocumentRepository(pool),
            store=store,
            retriever=HybridRetriever(
                store,
                embedder,
                rewriter=rewriter,
                enable_rewrite=settings.enable_query_rewrite,
            ),
            answerer=Answerer(
                FailoverLLM(providers=answering),
                verifier=verifier,
                enable_citation_binding=settings.enable_citation_binding,
                enable_verification=settings.enable_self_verification,
            ),
        )


def get_state(request: Request) -> AppState:
    state: AppState | None = getattr(request.app.state, "app_state", None)
    if state is None:
        # Development without a database, or a failed startup. Say which,
        # rather than letting the route fail on a None attribute deeper in.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "not_configured",
                "message": "The service is not connected to its database.",
            },
        )
    return state


State = Annotated[AppState, Depends(get_state)]
Config = Annotated[Settings, Depends(get_settings)]
