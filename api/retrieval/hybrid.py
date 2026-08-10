"""The retrieval pipeline: rewrite, embed, search both arms, fuse, assemble.

Chunks are re-retrieved on **every** turn and never carried forward from a
previous one. Reusing last turn's context is the cheap-looking optimisation that
makes chat RAG confidently wrong: the user asks a follow-up, the system answers
from passages retrieved for the *previous* question, and the answer is fluent,
on-topic and about the wrong clause.
"""

from __future__ import annotations

import asyncio
import re
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
from api.retrieval.floor import FloorVerdict
from api.retrieval.floor import evaluate as evaluate_floor
from api.retrieval.fusion import fuse
from api.retrieval.store import ChunkSearcher
from api.retrieval.types import RetrievedChunk

log = get_logger(__name__)

# The rewritten query is one line. Capping this hard keeps a cheap call cheap,
# and a rewrite that runs long has misunderstood the job anyway.
REWRITE_MAX_TOKENS = 120

# A first-turn question only pays for the understanding call if its shape says
# it needs one. Both numbers come from the golden set, which is the population
# of questions that already retrieve correctly: 70 questions, longest 81
# characters, 66 of them a single sentence.
#
# So a question over 96 characters is longer than anything that works today, and
# a second sentence is the shape that dilutes an embedding — a scenario followed
# by the actual question. The message this was built for is 109 characters and
# three sentences, and hits both.
#
# Erring toward not calling: a question that needs help and does not get it
# retrieves as it did before this existed, while one that gets help it did not
# need pays a call and a second of latency for nothing.
UNDERSTAND_MIN_CHARS = 96

# Below this, a rewrite is a fragment rather than a query. `deprem` measured
# 0.7538 against a floor of 0.72 — a single subject word is *further* from the
# document than the rambling question it replaced, because there is nothing
# around it to place it.
MIN_REWRITE_CHARS = 12

# A sentence ends where punctuation is followed by space or by nothing. The
# lookahead is the whole point: without it the dot in `Madde 4.1` is a sentence
# boundary, the query counts as two sentences, and an identifier — the one kind
# of query where paraphrasing destroys retrieval outright — gets sent to a
# rewriter. Figures like `1.800.000` fail the same way.
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def needs_understanding(question: str) -> bool:
    """Whether a first-turn question is shaped like prose rather than a query.

    Deliberately mechanical. A model asked "does this need rewriting?" is a
    second call to save the first one, and it would answer wrongly often enough
    to need its own evaluation.
    """
    if len(question.strip()) > UNDERSTAND_MIN_CHARS:
        return True
    return len([part for part in _SENTENCE_END.split(question) if part.strip()]) > 1


@dataclass(slots=True)
class RetrievalResult:
    context: AssembledContext
    candidates: list[RetrievedChunk] = field(default_factory=list)
    search_query: str = ""
    """What was actually searched for — the rewrite, if one happened."""

    rewritten: bool = False
    usage: list[UsageRecord] = field(default_factory=list)
    floor: FloorVerdict | None = None
    """Whether anything retrieved is about this document at all.

    Computed here because this is where the distances are, and acted on by the
    caller, because whether to answer is a decision about the request rather
    than about the search. `None` when the floor is switched off — which the
    eval does, to measure what it changes.
    """


class HybridRetriever:
    def __init__(
        self,
        store: ChunkSearcher,
        embedder: EmbeddingProvider,
        *,
        rewriter: LLMProvider | None = None,
        enable_rewrite: bool = True,
        enable_floor: bool = True,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._rewriter = rewriter
        self._enable_rewrite = enable_rewrite and rewriter is not None
        self._enable_floor = enable_floor

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
        # Judged on every candidate, not on the eight that survived assembly:
        # the question is whether the document has anything on this subject,
        # and trimming for the context window is about the prompt's budget.
        floor = evaluate_floor(candidates) if self._enable_floor else None

        log.info(
            "retrieval_complete",
            document_id=str(document_id),
            rewritten=rewritten,
            below_floor=floor.below if floor else None,
            best_distance=(
                round(floor.best_distance, 4) if floor and floor.best_distance is not None else None
            ),
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
            floor=floor,
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
        if not self._enable_rewrite or self._rewriter is None:
            return question, False, []
        if not history and not needs_understanding(question):
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

        # A rewrite that came back empty, that ballooned, or that collapsed has
        # misunderstood the task. The original question is a safe fallback; a
        # bad rewrite is not, because it steers retrieval at a passage the user
        # never asked about and does so invisibly.
        #
        # The collapse case was found in production rather than imagined. A
        # 109-character question came back as `dep` — one output token — and a
        # three-character query embeds nowhere near anything, so the floor
        # refused a question the document answers on page one. The stage meant
        # to help retrieval was breaking it, and the only symptom was a refusal
        # that looked exactly like every correct one.
        #
        # `MIN_REWRITE_CHARS` is deliberately small. A good rewrite is often far
        # shorter than the question — "deprem teminatı bina bedeli" against two
        # sentences of scenario — so this catches a fragment, not a summary, and
        # only for questions long enough to have triggered the stage.
        if not rewritten or len(rewritten) > len(question) * 6 + 200:
            log.warning("rewrite_rejected", reason="empty_or_ballooned")
            return question, False, usage
        if len(rewritten) < MIN_REWRITE_CHARS:
            log.warning(
                "rewrite_rejected",
                reason="collapsed",
                rewritten=rewritten,
                original_length=len(question),
            )
            return question, False, usage

        return rewritten, rewritten != question, usage
