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

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.deps import State
from api.generation.llm import Turn
from api.logging_config import get_logger
from api.pricing import UnpricedModelError, estimate_cost

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


def _event(name: str, payload: dict[str, object] | None = None) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload or {}, ensure_ascii=False)}


@router.post("/chat", summary="Ask a grounded question (SSE)")
async def chat(request: ChatRequest, state: State) -> EventSourceResponse:
    row = await state.pool.fetchrow(
        "select id, user_id, detected_lang from documents "
        "where id = $1 and is_sample and status = 'ready'",
        request.document_id,
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No such document, or it is not ready yet."
        )

    async def stream() -> AsyncIterator[dict[str, str]]:
        try:
            yield _event("retrieval_started")

            retrieved = await state.retriever.retrieve(
                question=request.question,
                document_id=UUID(str(row["id"])),
                user_id=UUID(str(row["user_id"])),
                history=[Turn(role=t.role, content=t.content) for t in request.history],  # type: ignore[arg-type]
            )
            yield _event(
                "retrieval_complete",
                {
                    "chunk_ids": [c.context_id for c in retrieved.context.chunks],
                    "count": len(retrieved.context.chunks),
                    "searched": retrieved.search_query,
                    "rewritten": retrieved.rewritten,
                },
            )

            yield _event("answering")
            outcome = await state.answerer.answer(
                question=request.question,
                context=retrieved.context,
                language=request.language,
            )
            answer = outcome.answer

            cost = 0.0
            for usage in [*retrieved.usage, *outcome.usage]:
                try:
                    cost += estimate_cost(
                        usage.model,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                    )
                except UnpricedModelError:
                    # Google is unpriced by design (see api/pricing.py). The
                    # figure shown to the user is therefore Anthropic-only, and
                    # the UI says so rather than implying it is the whole bill.
                    pass

            yield _event(
                "done",
                {
                    "answer": answer.answer,
                    "refused": answer.refused,
                    "suppressed": answer.suppressed,
                    "suppression_reason": answer.suppression_reason,
                    "confidence": answer.confidence,
                    "caveats": answer.caveats,
                    "groundedness": answer.groundedness,
                    "verified": answer.verified,
                    "citations": [
                        {
                            "context_id": c.context_id,
                            "quote": c.quote,
                            "page": c.page,
                            "section_path": c.section_path,
                            "bbox": c.bbox,
                            "exact": c.exact,
                        }
                        for c in answer.citations
                    ],
                    "dropped_citations": len(answer.dropped_citations),
                    "cost_usd": round(cost, 6),
                },
            )
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
