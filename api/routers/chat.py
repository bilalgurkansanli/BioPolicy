"""Grounded question answering over SSE.

The stream carries **stage events, not tokens** — see
[ADR 010](../../docs/adr/010-no-token-streaming.md). The short version: citation
binding and self-verification both run after generation and can withhold the
answer entirely. An answer already streamed into the user's view cannot be
withheld, only retracted, and a retracted claim is still a delivered claim.

So the answer arrives once, in `done`, after every check has run. The events
before it are real pipeline stages rather than a spinner with invented labels,
which is what makes the wait legible.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.answer_cache import CachedAnswer, is_cacheable
from api.auth import AuthenticatedUser, CurrentUser
from api.deps import AppState, Config, State
from api.generation import prompts
from api.generation.answerer import AnswerOutcome, off_topic_refusal
from api.generation.llm import Turn
from api.generation.schemas import GroundedAnswer
from api.logging_config import get_logger
from api.safety.limits import LimitExceededError

router = APIRouter(tags=["chat"])
log = get_logger(__name__)

MAX_QUESTION_CHARS = 1000


class HistoryTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    document_id: UUID
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    language: str = Field(default="tr", pattern="^(tr|en)$")
    # Bounded on purpose. Chunks are re-retrieved every turn and never carried
    # forward; only the conversation is, and only enough of it to resolve a
    # follow-up like "peki ya sel?".
    history: list[HistoryTurn] = Field(default_factory=list, max_length=8)
    # Which saved thread to append to. Honoured only if it belongs to this user
    # *and* this document; anything else starts a new one rather than failing.
    conversation_id: UUID | None = None


def _event(name: str, payload: dict[str, object] | None = None) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload or {}, ensure_ascii=False)}


# Enough to recognise a passage, not enough to read it here instead of in the
# document. The viewer is where a clause gets read; this is a label.
SNIPPET_CHARS = 180


def _snippet(content: str) -> str:
    flat = " ".join(content.split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[:SNIPPET_CHARS].rstrip() + "…"


def _answer_payload(
    answer: GroundedAnswer,
    conversation_id: UUID | None,
    cost: float,
    *,
    cached: int | None = None,
) -> dict[str, object]:
    """The `done` payload, in one place.

    Three paths produce it — the ordinary one, the floor's early refusal, and a
    cache hit — and a field added to only one of them is a field the client
    reads as `undefined` on the others.

    `cached` is the number of times this answer had been served before, or None
    if it was computed now. Not a boolean: "answered from cache" and "answered
    from cache for the 40th time" are different things to show someone reading a
    report that quotes per-question latency.
    """
    return {
        "conversation_id": str(conversation_id) if conversation_id else None,
        "cached": cached,
        "answer": answer.answer,
        "refused": answer.refused,
        "suppressed": answer.suppressed,
        "suppression_reason": answer.suppression_reason,
        "confidence": answer.confidence,
        "caveats": answer.caveats,
        "groundedness": answer.groundedness,
        "verified": answer.verified,
        "entailment": answer.entailment,
        "citations": [
            {
                "context_id": c.context_id,
                "quote": c.quote,
                "page": c.page,
                "page_end": c.page_end,
                "section_path": c.section_path,
                "bbox": c.bbox,
                "exact": c.exact,
            }
            for c in answer.citations
        ],
        "dropped_citations": len(answer.dropped_citations),
        "cost_usd": round(cost, 6),
    }


async def _serve_cached(
    hit: CachedAnswer,
    request: ChatRequest,
    user: AuthenticatedUser,
    state: AppState,
    row: Any,
) -> AsyncIterator[dict[str, str]]:
    """Replay a stored answer as the same sequence of events a fresh one sends.

    The client is not special-cased. It receives `retrieval_complete` with the
    passages that were considered when the answer was produced, and `done` with
    the answer — the difference is one labelled field, and no `answering` stage,
    because nothing is being answered.

    The turn is still written to the conversation. A question someone asked is
    in their history whether or not we had to pay to answer it.
    """
    payload = dict(hit.payload)
    considered = payload.pop("considered", [])

    yield _event(
        "retrieval_complete",
        {
            "chunk_ids": [c.get("context_id") for c in considered],
            "count": len(considered),
            "searched": request.question,
            "rewritten": False,
            "considered": considered,
        },
    )

    conversation_id: UUID | None = None
    try:
        conversation_id = await state.conversations.ensure(
            conversation_id=request.conversation_id,
            user_id=user.id,
            document_id=UUID(str(row["id"])),
            question=request.question,
        )
        await state.conversations.append_turn(
            conversation_id=conversation_id,
            user_id=user.id,
            question=request.question,
            answer=str(payload.get("answer", "")),
            citations=[],
            groundedness=cast(float | None, payload.get("groundedness")),
            refused=bool(payload.get("refused")),
            suppressed=bool(payload.get("suppressed")),
            prompt_version=str(payload.get("prompt_version", prompts.ANSWER)),
            model=str(payload.get("model", "")),
        )
    except Exception as exc:
        log.error("conversation_not_saved", exc_info=exc)

    payload["conversation_id"] = str(conversation_id) if conversation_id else None
    # Zero, and truthfully so: this answer cost nothing to serve. The figure the
    # interface shows has to stay a measurement of what was actually spent.
    payload["cost_usd"] = 0.0
    payload["cached"] = hit.served_before
    log.info("answer_served_from_cache", served_before=hit.served_before)
    yield _event("done", payload)


@router.post("/chat", summary="Ask a grounded question (SSE)")
async def chat(
    user: CurrentUser, request: ChatRequest, state: State, settings: Config
) -> EventSourceResponse:
    """Answer one question about one document.

    Every guard runs *before* the stream opens. An SSE response that has already
    begun can only report a limit as an `error` event, which the client has to
    special-case; a 429 before the first byte is a status code every HTTP client
    already understands.
    """
    row = await state.pool.fetchrow(
        "select id, user_id, detected_lang from documents "
        "where id = $1 and (is_sample or user_id = $2) and status = 'ready'",
        request.document_id,
        user.id,
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No such document, or it is not ready yet."
        )

    try:
        # Order matters: the global breaker first. When the demo is out of
        # money, telling a visitor they have questions left would be a lie.
        await state.breaker.ensure_capacity()
        await state.quota.ensure_can_ask(user.id)
    except LimitExceededError as exc:
        raise exc.as_http() from exc

    async def stream() -> AsyncIterator[dict[str, str]]:
        try:
            yield _event("retrieval_started")

            # Looked up before retrieval rather than after it, so a hit costs
            # nothing at all — not even the query embedding. The stored payload
            # carries the passages too, so the interface shows the same evidence
            # it would have shown for a fresh answer.
            #
            # A follow-up is never served from cache: its meaning depends on the
            # turns before it, and the key holds only the question as typed.
            hit = (
                None
                if request.history
                else await state.answer_cache.get(
                    document_id=UUID(str(row["id"])),
                    question=request.question,
                    language=request.language,
                    prompt_version=prompts.ANSWER,
                    model=settings.anthropic_model,
                )
            )
            if hit is not None:
                async for event in _serve_cached(hit, request, user, state, row):
                    yield event
                return

            retrieved = await state.retriever.retrieve(
                question=request.question,
                document_id=UUID(str(row["id"])),
                user_id=UUID(str(row["user_id"])),
                history=[Turn(role=t.role, content=t.content) for t in request.history],  # type: ignore[arg-type]
            )
            # Every passage that reached the prompt, so the interface can show
            # which of them the answer did not use. Built once: it is sent now,
            # as a fact about retrieval that stays true even if generation then
            # fails, and stored with the answer so a cache hit can replay it.
            considered = [
                {
                    "context_id": chunk.context_id,
                    "page": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section_path": chunk.section_path,
                    "snippet": _snippet(chunk.content),
                    # Carried so an unused passage can be opened in the viewer
                    # the way a cited one can. Without it the list would be
                    # readable and unverifiable, which is the opposite of the
                    # point.
                    "bbox": chunk.bbox.as_dict() if chunk.bbox else None,
                }
                for chunk in retrieved.context.chunks
            ]
            yield _event(
                "retrieval_complete",
                {
                    "chunk_ids": [c.context_id for c in retrieved.context.chunks],
                    "count": len(retrieved.context.chunks),
                    "searched": retrieved.search_query,
                    "rewritten": retrieved.rewritten,
                    "considered": considered,
                },
            )

            # The floor: nothing retrieved is about this subject, so there is
            # nothing to answer from and no reason to pay a model to say so.
            # Deliberately after `retrieval_complete` — the client has already
            # been told what was searched and what came back, and a refusal that
            # arrives with that evidence attached is inspectable.
            if retrieved.floor is not None and retrieved.floor.below:
                log.info("refused_below_floor", **retrieved.floor.as_dict)
                outcome = off_topic_refusal(request.language)
                yield _event("done", _answer_payload(outcome.answer, None, 0.0))
                return

            yield _event("answering")

            # Answering is run as a task so its internal stage transitions can
            # be forwarded while it is still in flight. Awaiting it directly
            # would leave the client on "answering" for the whole call —
            # including verification, which is roughly half the wait. A stage
            # the interface shows but never reaches is the spinner with an
            # invented label that ADR 010 argues against.
            stages: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()

            async def run() -> AnswerOutcome:
                try:
                    return await state.answerer.answer(
                        question=request.question,
                        context=retrieved.context,
                        language=request.language,
                        on_stage=lambda name: stages.put(_event(name)),
                    )
                finally:
                    # Unblocks the drain below on every path, including failure.
                    await stages.put(None)

            answering = asyncio.create_task(run())
            while (stage := await stages.get()) is not None:
                yield stage

            outcome = await answering
            answer = outcome.answer

            # Saved before the `done` event, so a conversation the user can see
            # on screen is one they will also find in their history. A failure
            # here must not lose the answer, though — it is caught and logged
            # rather than turning a paid-for reply into an error.
            conversation_id: UUID | None = None
            try:
                conversation_id = await state.conversations.ensure(
                    conversation_id=request.conversation_id,
                    user_id=user.id,
                    document_id=UUID(str(row["id"])),
                    question=request.question,
                )
                await state.conversations.append_turn(
                    conversation_id=conversation_id,
                    user_id=user.id,
                    question=request.question,
                    answer=answer.answer,
                    citations=answer.citations,
                    groundedness=answer.groundedness,
                    refused=answer.refused,
                    suppressed=answer.suppressed,
                    prompt_version=outcome.prompt_version,
                    model=outcome.model,
                )
            # The answer is already paid for and correct; losing the copy in
            # someone's history is the lesser failure.
            except Exception as exc:
                log.error("conversation_not_saved", exc_info=exc)

            # The ledger is written even when the answer was suppressed: a
            # withheld answer still cost money, and the breaker has to see it.
            # `record` prices as it writes, so Google's unpriced calls are
            # stored with their tokens and a zero — the figure shown to the user
            # is therefore Anthropic-only, and the interface says so.
            cost = await state.usage.record(
                user_id=user.id, records=[*retrieved.usage, *outcome.usage]
            )
            state.breaker.note_spend(cost)

            payload = _answer_payload(answer, conversation_id, cost)

            # Stored with the passages, so a hit can replay the whole stream.
            # `conversation_id` and `cost_usd` are overwritten on the way out —
            # they belong to the request, not to the answer.
            if is_cacheable(payload):
                await state.answer_cache.put(
                    document_id=UUID(str(row["id"])),
                    question=request.question,
                    language=request.language,
                    prompt_version=outcome.prompt_version,
                    model=settings.anthropic_model,
                    payload={
                        **payload,
                        "considered": considered,
                        "prompt_version": outcome.prompt_version,
                        "model": outcome.model,
                    },
                )

            yield _event("done", payload)
        except Exception as exc:  # the stream must end with an event, not a hang
            log.error("chat_failed", exc_info=exc)
            yield _event(
                "error",
                {
                    "code": "internal_error",
                    "message": "Something went wrong. Nothing was charged for a failed answer.",
                },
            )

    return EventSourceResponse(stream())
