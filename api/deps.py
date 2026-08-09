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

from api.accounts import AccountRepository
from api.config import Settings, get_settings
from api.conversations import ConversationRepository
from api.documents import DocumentRepository
from api.generation.answerer import Answerer
from api.generation.entailment import EntailmentChecker
from api.generation.llm import FailoverLLM, LLMProvider
from api.generation.profile import PROFILE_JSON_SCHEMA, ProfileExtractor
from api.generation.providers import AnthropicLLM, GeminiLLM
from api.generation.schemas import (
    ANSWER_JSON_SCHEMA,
    ENTAILMENT_JSON_SCHEMA,
    VERIFICATION_JSON_SCHEMA,
)
from api.generation.verifier import Verifier
from api.identity import IdentityService
from api.ingest.chunker import Chunker
from api.ingest.ocr.gemini import GeminiOCR
from api.ingest.parsers.native import PdfParser
from api.ingest.pipeline import IngestionPipeline
from api.ingest.worker import IngestionWorker
from api.logging_config import get_logger
from api.retention import RetentionService
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import ChunkStore
from api.safety.breaker import BudgetBreaker
from api.safety.quota import QuotaGuard
from api.storage import VIEW_URL_TTL_SECONDS, DocumentStorage
from api.usage import UsageRepository

log = get_logger(__name__)


@dataclass(slots=True)
class AppState:
    """Everything built once at startup and shared across requests."""

    pool: asyncpg.Pool
    documents: DocumentRepository
    store: ChunkStore
    retriever: HybridRetriever
    answerer: Answerer
    profiler: ProfileExtractor
    storage: DocumentStorage
    usage: UsageRepository
    accounts: AccountRepository
    identity: IdentityService
    conversations: ConversationRepository
    quota: QuotaGuard
    breaker: BudgetBreaker
    retention: RetentionService
    worker: IngestionWorker
    storage_view_ttl: int = VIEW_URL_TTL_SECONDS

    @classmethod
    def build(cls, pool: asyncpg.Pool, settings: Settings) -> AppState:
        embedder = GeminiEmbedder(settings.google_api_key or "", settings.gemini_embedding_model)
        store = ChunkStore(pool)
        documents = DocumentRepository(pool)
        storage = DocumentStorage(settings)
        usage = UsageRepository(pool)
        accounts = AccountRepository(pool, unlimited_emails=frozenset(settings.unlimited_emails))

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

        # Typed extraction gets its own provider chain rather than sharing the
        # answerer's, because the enforced schema differs — one returns an
        # answer with citations, the other a list of slot fillings. A single
        # client cannot carry both.
        profiling: list[LLMProvider] = [
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=PROFILE_JSON_SCHEMA,
            )
        ]
        if settings.google_api_key and settings.gemini_fallback_model:
            profiling.append(
                GeminiLLM(
                    settings.google_api_key,
                    settings.gemini_fallback_model,
                    json_schema=PROFILE_JSON_SCHEMA,
                )
            )

        verifier = Verifier(
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=VERIFICATION_JSON_SCHEMA,
            )
        )

        entailment = EntailmentChecker(
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=ENTAILMENT_JSON_SCHEMA,
            )
        )

        # OCR is optional: without a verified model id the parser handles native
        # PDFs and fails scanned ones with a message saying so (ADR 004).
        ocr = (
            GeminiOCR(settings.google_api_key, settings.gemini_ocr_model)
            if settings.google_api_key and settings.gemini_ocr_model
            else None
        )

        return cls(
            pool=pool,
            documents=documents,
            store=store,
            storage=storage,
            usage=usage,
            retriever=HybridRetriever(
                store,
                embedder,
                rewriter=rewriter,
                enable_rewrite=settings.enable_query_rewrite,
                enable_floor=settings.enable_retrieval_floor,
            ),
            answerer=Answerer(
                FailoverLLM(providers=answering),
                verifier=verifier,
                entailment=entailment,
                enable_citation_binding=settings.enable_citation_binding,
                enable_verification=settings.enable_self_verification,
                enable_entailment_check=settings.enable_entailment_check,
            ),
            profiler=ProfileExtractor(FailoverLLM(providers=profiling)),
            accounts=accounts,
            identity=IdentityService(settings),
            conversations=ConversationRepository(pool),
            quota=QuotaGuard(
                pool,
                usage,
                accounts,
                daily_questions=settings.user_daily_message_limit,
                daily_documents=settings.user_daily_document_limit,
            ),
            breaker=BudgetBreaker(usage, limit_usd=settings.global_budget_usd),
            retention=RetentionService(pool, storage),
            worker=IngestionWorker(
                documents=documents,
                pipeline=IngestionPipeline(
                    documents=documents,
                    store=store,
                    parser=PdfParser(ocr=ocr),
                    embedder=embedder,
                    chunker=Chunker(),
                ),
                storage=storage,
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
