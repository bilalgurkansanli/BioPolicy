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
from api.answer_cache import AnswerCache
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
from api.retrieval.embedder import EmbeddingProvider
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import ChunkStore
from api.retrieval.voyage_embedder import VoyageEmbedder
from api.safety.breaker import BudgetBreaker
from api.safety.quota import QuotaGuard
from api.storage import VIEW_URL_TTL_SECONDS, DocumentStorage
from api.usage import UsageRepository

log = get_logger(__name__)


def embedding_model(settings: Settings) -> str:
    """Which model `build_embedder` would use, without building anything.

    Exists because two callers need the *name* and nothing else — the retrieval
    floor's model check, and `/api/health` reporting what is in force — and
    building a provider to read one string is not free. `GeminiEmbedder`'s
    constructor builds a genai client, and that client raises `ValueError` when
    no key is set.

    That turned the one route whose job is to explain a broken configuration
    into a 500 on exactly the configuration it exists to explain, and it did so
    on an unauthenticated endpoint. `test_the_name_matches_what_gets_built`
    pins the two together.
    """
    return settings.voyage_model if settings.voyage_api_key else settings.gemini_embedding_model


def build_rewriter(settings: Settings) -> LLMProvider | None:
    """The model that turns a question into a search query.

    A function beside `build_embedder`, and for the same reason: every copy of
    this choice is a copy that drifts. `api/scripts/ask.py` held one, and it has
    now been wrong three separate times — once with the embedder, once by
    omitting the rewriter entirely, once by keeping the provider this moved
    away from. Each time the script reported the pipeline's behaviour
    confidently and incorrectly, which is worse than not reporting it.

    Anthropic first. The fallback provider was tried here and measured unfit:
    20 requests a day on its free tier, and replies of one to five tokens — a
    109-character question came back as `dep`. A three-character query embeds
    nowhere near the document, so the retrieval floor then refuses a question
    the document answers on page one.
    """
    if settings.anthropic_api_key:
        return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)
    if settings.google_api_key and settings.gemini_fallback_model:
        return GeminiLLM(settings.google_api_key, settings.gemini_fallback_model)
    return None


def build_embedder(settings: Settings) -> EmbeddingProvider:
    """Voyage when it is configured, Gemini otherwise.

    Not a failover chain — one document's vectors must all come from one model,
    since a vector is only meaningful in the space that produced it. This picks
    a provider once, at startup, and stays with it.

    Both are configured to the same width, so the column fits either and a
    deployment that switches gets an obvious failure at insert time rather than
    a subtly wrong distance. What it does *not* get is correct results: swapping
    providers means re-embedding everything (ADR 016, migration 0012).
    """
    if settings.voyage_api_key:
        return VoyageEmbedder(
            settings.voyage_api_key,
            settings.voyage_model,
            # Passed rather than left to the constructor's defaults. They were
            # defaulted here once and it made the pacing unconfigurable: an
            # account that had lifted its ceiling with the provider still
            # embedded at 10K tokens a minute, because the ceiling is enforced
            # on both sides and only one of them had moved.
            requests_per_minute=settings.voyage_requests_per_minute,
            tokens_per_minute=settings.voyage_tokens_per_minute,
        )

    log.warning(
        "embedding_fallback_provider",
        detail=(
            "VOYAGE_API_KEY is unset, so embeddings use Gemini. Its free tier "
            "allows 1,000 passages a day and a 27-page policy is ~130 of them."
        ),
    )
    return GeminiEmbedder(
        settings.google_api_key or "",
        settings.gemini_embedding_model,
        texts_per_minute=settings.embed_texts_per_minute,
    )


@dataclass(slots=True)
class AppState:
    """Everything built once at startup and shared across requests."""

    pool: asyncpg.Pool
    documents: DocumentRepository
    answer_cache: AnswerCache
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
        embedder = build_embedder(settings)
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

        rewriter = build_rewriter(settings)

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
            answer_cache=AnswerCache(pool, enabled=settings.enable_answer_cache),
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
