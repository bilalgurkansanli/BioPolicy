"""Raw SQL against Postgres. No ORM, no query builder.

## Access control is in every query, not delegated to RLS

The API holds a service-role key, which bypasses row-level security entirely.
The policies in migration 0005 protect against a leaked anon key and a future
direct-from-browser query; they do **not** protect against a missing `WHERE`
clause here.

So every statement in this module carries its own access predicate: a chunk is
readable if its document belongs to the requester, or if the document is a
bundled sample. That predicate is inside the same SQL statement as the search,
not a separate check before it — a separate check is a race and an easy thing to
forget on a new code path.

## The Turkish text-search configuration is probed, not assumed

Migration 0003 builds `fts_tr` with `turkish` if the server has it and `simple`
otherwise. The query side must use the *same* configuration or `@@` silently
matches nothing — no error, just a keyword arm that always returns zero rows and
a hybrid search quietly reduced to pure vector. We ask the server once and cache
the answer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import asyncpg

from api.constants import (
    EMBEDDING_DIM,
    KEYWORD_CANDIDATES,
    VECTOR_CANDIDATES,
)
from api.ingest.chunker import Chunk
from api.ingest.types import BBox
from api.logging_config import get_logger
from api.retrieval.types import RetrievedChunk

log = get_logger(__name__)


def to_pgvector(values: list[float]) -> str:
    """Render a vector for pgvector.

    asyncpg has no native codec for the `vector` type, so it travels as text and
    is cast in the statement. The format is exact: square brackets, comma
    separated, no spaces.
    """
    if len(values) != EMBEDDING_DIM:
        raise ValueError(f"expected {EMBEDDING_DIM} dimensions, got {len(values)}")
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


# WHY one statement rather than two round trips: both arms are scoped to the
# same document and the same access check. Issuing them separately doubles the
# latency, doubles the planning cost, and opens a window where the document's
# access state could change between them.
#
# `row_number()` is what turns each arm into ranks, which is all RRF consumes —
# the raw distances and ts_rank scores are deliberately left behind, since they
# are on incomparable scales (see fusion.py).
_HYBRID_SQL = """
with accessible as (
    select d.id
    from documents d
    where d.id = $1
      and d.status = 'ready'
      and (d.is_sample or d.user_id = $2)
),
vector_arm as (
    select c.id, row_number() over (order by c.embedding <=> $3::vector) as rank
    from chunks c
    join accessible a on a.id = c.document_id
    order by c.embedding <=> $3::vector
    limit $5
),
keyword_arm as (
    select id, row_number() over (order by score desc, id) as rank
    from (
        select c.id,
               greatest(
                   ts_rank_cd(c.fts_tr, websearch_to_tsquery($7::regconfig, $4)),
                   ts_rank_cd(c.fts_en, websearch_to_tsquery('english', $4))
               ) as score
        from chunks c
        join accessible a on a.id = c.document_id
        where c.fts_tr @@ websearch_to_tsquery($7::regconfig, $4)
           or c.fts_en @@ websearch_to_tsquery('english', $4)
    ) ranked
    order by score desc, id
    limit $6
)
select c.id, c.content, c.content_type, c.page_start, c.page_end,
       c.section_path, c.bbox,
       v.rank as vector_rank, k.rank as keyword_rank
from chunks c
left join vector_arm  v on v.id = c.id
left join keyword_arm k on k.id = c.id
where v.id is not null or k.id is not null
"""

_INSERT_SQL = """
insert into chunks (
    document_id, user_id, ordinal, content, content_type,
    page_start, page_end, bbox, section_path, token_count, embedding
) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::vector)
"""


@runtime_checkable
class ChunkSearcher(Protocol):
    """The read side of the store, which is all the retriever needs.

    Narrow on purpose: it lets the retriever be tested against an in-memory
    fake, and it stops write methods leaking into a read path.
    """

    async def hybrid_search(
        self,
        *,
        document_id: UUID,
        user_id: UUID | None,
        query_embedding: list[float],
        query_text: str,
        vector_limit: int = ...,
        keyword_limit: int = ...,
    ) -> list[RetrievedChunk]: ...


class ChunkStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._tr_config: str | None = None

    async def turkish_config(self) -> str:
        """Which text-search configuration `fts_tr` was actually built with."""
        if self._tr_config is None:
            exists = await self._pool.fetchval(
                "select exists (select 1 from pg_ts_config where cfgname = 'turkish')"
            )
            self._tr_config = "turkish" if exists else "simple"
            if not exists:
                log.warning(
                    "turkish_fts_unavailable",
                    detail=(
                        "Falling back to 'simple'. Turkish keyword retrieval will not "
                        "stem; expect the eval to show it. Record in an ADR."
                    ),
                )
        return self._tr_config

    # -------------------------------------------------------------------------
    # write
    # -------------------------------------------------------------------------

    async def replace_chunks(
        self,
        *,
        document_id: UUID,
        user_id: UUID,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> int:
        """Write a document's chunks, replacing anything already stored.

        Delete-then-insert inside one transaction, because ingestion is
        retryable (ADR 007). A retry that appended instead of replacing would
        silently double every chunk, and duplicated chunks are worse than
        missing ones: they crowd out other content in retrieval while adding
        nothing.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"{len(chunks)} chunks but {len(embeddings)} embeddings — refusing to "
                "write a document whose vectors do not line up with its text"
            )

        rows = [
            (
                document_id,
                user_id,
                chunk.ordinal,
                chunk.content,
                chunk.content_type,
                chunk.page_start,
                chunk.page_end,
                _bbox_json(chunk.bbox),
                chunk.section_path,
                chunk.token_count,
                to_pgvector(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]

        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute("delete from chunks where document_id = $1", document_id)
            await connection.executemany(_INSERT_SQL, rows)

        log.info("chunks_written", document_id=str(document_id), count=len(rows))
        return len(rows)

    # -------------------------------------------------------------------------
    # read
    # -------------------------------------------------------------------------

    async def hybrid_search(
        self,
        *,
        document_id: UUID,
        user_id: UUID | None,
        query_embedding: list[float],
        query_text: str,
        vector_limit: int = VECTOR_CANDIDATES,
        keyword_limit: int = KEYWORD_CANDIDATES,
    ) -> list[RetrievedChunk]:
        """Both retrieval arms, one round trip, scoped and access-checked.

        `user_id` may be None for an anonymous visitor, who can still reach the
        bundled samples — the access predicate handles that case rather than the
        caller.
        """
        rows = await self._pool.fetch(
            _HYBRID_SQL,
            document_id,
            user_id,
            to_pgvector(query_embedding),
            query_text,
            vector_limit,
            keyword_limit,
            await self.turkish_config(),
        )
        return [_to_chunk(row) for row in rows]

    async def chunk_count(self, document_id: UUID) -> int:
        count: int = await self._pool.fetchval(
            "select count(*) from chunks where document_id = $1", document_id
        )
        return count


def _bbox_json(bbox: BBox | None) -> str | None:
    if bbox is None:
        return None
    import json

    return json.dumps(bbox.as_dict())


def _to_chunk(row: Any) -> RetrievedChunk:
    bbox = row["bbox"]
    if isinstance(bbox, str):
        import json

        bbox = json.loads(bbox)

    return RetrievedChunk(
        chunk_id=row["id"],
        content=row["content"],
        content_type=row["content_type"],
        page_start=row["page_start"] or 1,
        page_end=row["page_end"] or row["page_start"] or 1,
        section_path=row["section_path"] or "",
        bbox=BBox(**bbox) if bbox else None,
        vector_rank=row["vector_rank"],
        keyword_rank=row["keyword_rank"],
    )
