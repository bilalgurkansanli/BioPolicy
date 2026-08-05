"""The retrieval pipeline: rewrite, embed, search both arms, fuse, assemble.

Chunks are re-retrieved on **every** turn and never carried forward from a
previous one. Reusing last turn's context is the cheap-looking optimisation that
makes chat RAG confidently wrong: the user asks a follow-up, the system answers
from passages retrieved for the *previous* question, and the answer is fluent,
on-topic and about the wrong clause.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from api.constants import (
    CONTEXT_CHUNK_COUNT,
    MEMORY_VERBATIM_TURNS,
    QUERY_REWRITE_TIMEOUT_SECONDS,
)
from api.generation import prompts
from api.generation.llm import LLMProvider, ProviderError, Turn, UsageRecord
from api.logging_config import get_logger
from api.retrieval.context import AssembledContext, assemble
from api.retrieval.embedder import EmbeddingProvider
from api.retrieval.fusion import fuse
from api.retrieval.store import ChunkSearcher
from api.retrieval.types import RetrievedChunk

log = get_logger(__name__)

# The rewritten query is one line. Capping this hard keeps a cheap call cheap,
# and a rewrite that runs long has misunderstood the job anyway.
REWRITE_MAX_TOKENS = 120


@dataclass(slots=True)
class RetrievalResult:
    context: AssembledContext
    candidates: list[RetrievedChunk] = field(default_factory=list)
    search_query: str = ""
    """What was actually searched for — the rewrite, if one happened."""

    rewritten: bool = False
    usage: list[UsageRecord] = field(default_factory=list)


class HybridRetriever:
    def __init__(
        self,
        store: ChunkSearcher,
        embedder: EmbeddingProvider,
        *,
        rewriter: LLMProvider | None = None,
        enable_rewrite: bool = True,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._rewriter = rewriter
        self._enable_rewrite = enable_rewrite and rewriter is not None

    async def retrieve(
        self,
        *,
        question: str,
        document_id: UUID,
        user_id: UUID | None,
        history: list[Turn] | None = None,
        max_chunks: int = CONTEXT_CHUNK_COUNT,
    ) -> RetrievalResult:
        usage: list[UsageRecord] = []
        history = history or []

        search_query, rewritten, rewrite_usage = await self._resolve_query(question, history)
        usage.extend(rewrite_usage)

        # WHY the query is embedded with the query task type: Gemini embeds
        # asymmetrically, and a question is not the same kind of text as the
        # passage that answers it. Using the document task type here produces no
        # error and quietly costs recall.
        query_vector = await self._embedder.embed_query(search_query)

        candidates = await self._store.hybrid_search(
            document_id=document_id,
            user_id=user_id,
            query_embedding=query_vector,
            query_text=search_query,
        )

        ranked = fuse(candidates)
        context = assemble(ranked, max_chunks=max_chunks)

        log.info(
            "retrieval_complete",
            document_id=str(document_id),
            rewritten=rewritten,
            candidates=len(candidates),
            vector_only=sum(1 for c in candidates if c.keyword_rank is None),
            keyword_only=sum(1 for c in candidates if c.vector_rank is None),
            both_arms=sum(
                1 for c in candidates if c.vector_rank is not None and c.keyword_rank is not None
            ),
            in_context=len(context.chunks),
            context_tokens=context.token_count,
        )

        return RetrievalResult(
            context=context,
            candidates=ranked,
            search_query=search_query,
            rewritten=rewritten,
            usage=usage,
        )

    async def _resolve_query(
        self, question: str, history: list[Turn]
    ) -> tuple[str, bool, list[UsageRecord]]:
        """Turn a context-dependent follow-up into a standalone query.

        "peki ya sel?" embedded as written retrieves nothing useful. Resolving
        it against the last few turns is the highest-leverage fix for multi-turn
        retrieval and costs one small call.

        A failure here is not fatal: we fall back to the question as typed,
        which is what a system without rewriting would have used anyway. That
        fallback is also why the call gets its own short timeout — being slow is
        a failure mode too, and the user is already waiting with nothing on
        screen until every check has run (ADR 010).
        """
        if not self._enable_rewrite or not history or self._rewriter is None:
            return question, False, []

        recent = history[-MEMORY_VERBATIM_TURNS * 2 :]
        transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in recent)

        try:
            async with asyncio.timeout(QUERY_REWRITE_TIMEOUT_SECONDS):
                response = await self._rewriter.complete(
                    system="You rewrite follow-up questions into standalone search queries.",
                    turns=[
                        Turn(
                            role="user",
                            content=prompts.render(
                                prompts.REWRITE, history=transcript, question=question
                            ),
                        )
                    ],
                    max_tokens=REWRITE_MAX_TOKENS,
                    temperature=0.0,
                )
        except ProviderError as exc:
            log.warning("rewrite_unavailable", error=str(exc))
            return question, False, []
        except TimeoutError:
            # No usage is recorded: the call was abandoned, and billing for it
            # is the provider's business, not something we can measure.
            log.warning("rewrite_timed_out", seconds=QUERY_REWRITE_TIMEOUT_SECONDS)
            return question, False, []

        rewritten = response.text.strip().strip('"').strip()
        usage = [UsageRecord.from_response("rewrite", response)]

        # A rewrite that came back empty, or that ballooned, has misunderstood
        # the task. The original question is a safe fallback; a bad rewrite is
        # not, because it steers retrieval at a passage the user never asked
        # about and does so invisibly.
        if not rewritten or len(rewritten) > len(question) * 6 + 200:
            log.warning("rewrite_rejected", original_length=len(question))
            return question, False, usage

        return rewritten, rewritten != question, usage
