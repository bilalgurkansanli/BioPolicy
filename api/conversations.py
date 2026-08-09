"""Saved conversations.

Chats are kept so a signed-in visitor can come back to one. That is a change of
promise, not just a feature: the interface used to say questions were never
stored, and it now says they are kept in your account until you delete them.
Both sentences cannot be true, and the one on screen has been changed to the one
the code does.

## What still expires

Nothing here outlives its document. `conversations.document_id` cascades, so an
uploaded policy taking its conversation with it after 24 hours is the database's
behaviour rather than a job that has to remember. Conversations about the sample
documents last until their owner deletes them, because the samples do.

## Scoping

Every query is filtered by `user_id` in SQL, not by RLS. The API holds a
service-role key and bypasses every policy, so a query that forgot the clause
would read other people's chats and no policy would stop it. The filter is in
the statement, on every statement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from api.logging_config import get_logger

log = get_logger(__name__)

# What the sidebar lists. Enough to find a conversation from last week, few
# enough that the query stays a single index scan.
MAX_LISTED = 50

# A title is the first question, cut. Long enough to recognise, short enough to
# sit in a narrow column.
TITLE_CHARS = 60


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    id: UUID
    title: str
    document_id: UUID
    document_filename: str
    document_exists: bool
    updated_at: datetime
    message_count: int


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    groundedness: float | None
    refused: bool
    suppressed: bool
    created_at: datetime


def title_from(question: str) -> str:
    cleaned = " ".join(question.split())
    if len(cleaned) <= TITLE_CHARS:
        return cleaned
    return cleaned[: TITLE_CHARS - 1].rstrip() + "…"


class ConversationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure(
        self, *, conversation_id: UUID | None, user_id: UUID, document_id: UUID, question: str
    ) -> UUID:
        """Return the conversation to append to, creating one if needed.

        A supplied id is honoured only if it belongs to this user *and* to this
        document. Both halves matter: the first stops one visitor writing into
        another's history, and the second stops a conversation about one policy
        collecting answers about a different one, which would make every stored
        citation unverifiable against the document the chat claims to be about.
        """
        if conversation_id is not None:
            row = await self._pool.fetchrow(
                """
                update conversations set updated_at = now()
                 where id = $1 and user_id = $2 and document_id = $3
                 returning id
                """,
                conversation_id,
                user_id,
                document_id,
            )
            if row is not None:
                return UUID(str(row["id"]))
            # Falls through to a new conversation rather than raising: the id
            # may simply belong to a document the user has since deleted, and
            # refusing to answer over that is a worse outcome than starting a
            # fresh thread.
            log.info("conversation_not_reused", user_id=str(user_id))

        row = await self._pool.fetchrow(
            """
            insert into conversations (user_id, document_id, title)
            values ($1, $2, $3)
            returning id
            """,
            user_id,
            document_id,
            title_from(question),
        )
        return UUID(str(row["id"]))

    async def append_turn(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        question: str,
        answer: str,
        citations: Sequence[Mapping[str, Any]],
        groundedness: float | None,
        refused: bool,
        suppressed: bool,
        prompt_version: str,
        model: str,
    ) -> None:
        """Store one exchange.

        Both messages go in one transaction. A question saved without its
        answer would come back as a conversation that appears to have been
        ignored.

        Citations arrive already serialised rather than as `BoundCitation`.
        Two paths reach here and only one of them has the objects: an answer
        replayed from the cache has the same citations as JSON and cannot
        reconstruct them, because `chunk_id` is not part of what the client was
        sent. Taking dictionaries lets both paths store the same thing — the
        alternative, which was what shipped, was passing an empty list from the
        cached path and silently losing every citation from a user's history.
        """
        payload = list(citations)

        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """
                insert into messages (conversation_id, user_id, role, content)
                values ($1, $2, 'user', $3)
                """,
                conversation_id,
                user_id,
                question,
            )
            await connection.execute(
                """
                insert into messages (
                    conversation_id, user_id, role, content,
                    citations, groundedness_score, refused, suppressed,
                    prompt_version, model
                ) values ($1, $2, 'assistant', $3, $4::jsonb, $5, $6, $7, $8, $9)
                """,
                conversation_id,
                user_id,
                answer,
                _json(payload),
                groundedness,
                refused,
                suppressed,
                prompt_version,
                model,
            )
            await connection.execute(
                "update conversations set updated_at = now() where id = $1", conversation_id
            )

    async def list_for(
        self, user_id: UUID, *, limit: int = MAX_LISTED
    ) -> list[ConversationSummary]:
        rows = await self._pool.fetch(
            """
            select c.id,
                   coalesce(c.title, '') as title,
                   c.document_id,
                   coalesce(d.filename, '') as document_filename,
                   d.id is not null as document_exists,
                   c.updated_at,
                   (select count(*) from messages m where m.conversation_id = c.id) as message_count
              from conversations c
              left join documents d on d.id = c.document_id
             where c.user_id = $1
             order by c.updated_at desc
             limit $2
            """,
            user_id,
            limit,
        )
        return [
            ConversationSummary(
                id=row["id"],
                title=row["title"],
                document_id=row["document_id"],
                document_filename=row["document_filename"],
                document_exists=row["document_exists"],
                updated_at=row["updated_at"],
                message_count=int(row["message_count"]),
            )
            for row in rows
        ]

    async def messages(self, conversation_id: UUID, user_id: UUID) -> list[StoredMessage] | None:
        """One conversation's turns, or `None` if it is not this user's.

        `None` rather than an empty list: a conversation someone else owns and
        one that happens to be empty are different answers, and only the second
        should render as an empty thread.
        """
        owned = await self._pool.fetchval(
            "select 1 from conversations where id = $1 and user_id = $2",
            conversation_id,
            user_id,
        )
        if owned is None:
            return None

        rows = await self._pool.fetch(
            """
            select id, role, content, citations, groundedness_score, refused, suppressed, created_at
              from messages
             where conversation_id = $1 and user_id = $2
             order by created_at, id
            """,
            conversation_id,
            user_id,
        )
        return [
            StoredMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                citations=_loads(row["citations"]),
                groundedness=row["groundedness_score"],
                refused=row["refused"],
                suppressed=row["suppressed"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def delete(self, conversation_id: UUID, user_id: UUID) -> bool:
        """Messages cascade; the ownership clause is what makes this safe."""
        row = await self._pool.fetchrow(
            "delete from conversations where id = $1 and user_id = $2 returning id",
            conversation_id,
            user_id,
        )
        return row is not None


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(value: object) -> list[dict[str, Any]]:
    if isinstance(value, str):
        parsed = json.loads(value or "[]")
    else:
        parsed = value or []
    return parsed if isinstance(parsed, list) else []
