"""Saved conversations: list, open, delete.

Everything here is owner-scoped in SQL rather than by RLS, because the API holds
a service-role key and bypasses every policy. A conversation belonging to
someone else answers 404, not 403 — whether an id exists is not something a
stranger should be able to probe.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.auth import CurrentUser
from api.deps import State

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    document_id: UUID
    document_filename: str
    document_exists: bool
    """False once the document expired or was deleted. The chat outlives it."""

    updated_at: datetime
    message_count: int


class Message(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    groundedness: float | None
    refused: bool
    suppressed: bool
    created_at: datetime


class Conversation(BaseModel):
    id: UUID
    messages: list[Message]


@router.get("", response_model=list[ConversationSummary], summary="Your conversations")
async def index(user: CurrentUser, state: State) -> list[ConversationSummary]:
    return [
        ConversationSummary(**asdict(summary))
        for summary in await state.conversations.list_for(user.id)
    ]


@router.get("/{conversation_id}", response_model=Conversation, summary="Open one")
async def show(conversation_id: UUID, user: CurrentUser, state: State) -> Conversation:
    messages = await state.conversations.messages(conversation_id, user.id)
    if messages is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such conversation.")
    return Conversation(
        id=conversation_id, messages=[Message(**asdict(message)) for message in messages]
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete one")
async def destroy(conversation_id: UUID, user: CurrentUser, state: State) -> None:
    if not await state.conversations.delete(conversation_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such conversation.")
