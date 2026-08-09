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
from api.ingest.types import BBox, OcrLine
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
# the raw ts_rank score is deliberately left behind, since the two arms' scores
# are on incomparable scales (see fusion.py).
#
# The cosine distance is the one exception, and it is carried out of the vector
# arm for a purpose fusion has no use for: deciding whether anything here is
# relevant *at all*. Ranks cannot answer that question. Something is always at
# rank 1, so RRF gives an irrelevant question the same top score as a good one.
# Cosine distance is absolute — the same 0.42 means the same thing on any
# question — which is what a floor needs. See `api/retrieval/floor.py`.
#
# ---------------------------------------------------------------------------
# WHY the `& -> |` rewrite on the tsquery, which is the least obvious line here
# ---------------------------------------------------------------------------
# `websearch_to_tsquery` joins every term with AND. For a search box — where a
# user types two or three keywords — that is exactly right. For a natural
# language question it is fatal:
#
#     websearch_to_tsquery('turkish', 'Deprem hasarında bana ne kadar ödenir?')
#       -> 'depre' & 'hasar' & 'ba' & 'kadar' & 'ödenir'
#
# That demands a single chunk containing all five stems. No chunk does, so the
# arm returns zero rows — with no error, no warning, and a hybrid search
# quietly degraded to pure vector. It was found only by noticing that live
# results never carried a keyword rank.
#
# Rewriting the connective to OR makes every term optional and lets
# `ts_rank_cd` do what it is for: score a chunk by how many of them it matched,
# and how close together. Stemming, stop-word removal and phrase groups
# (`<->`, from quoted input) all survive the rewrite untouched — only the
# top-level connective changes.
_HYBRID_SQL = """
with accessible as (
    select d.id
    from documents d
    where d.id = $1
      and d.status = 'ready'
      and (d.is_sample or d.user_id = $2)
),
q as (
    select
        replace(websearch_to_tsquery($7::regconfig, $4)::text, ' & ', ' | ')::tsquery as tr,
        replace(websearch_to_tsquery('english', $4)::text, ' & ', ' | ')::tsquery as en
),
vector_arm as (
    select c.id,
           row_number() over (order by c.embedding <=> $3::vector) as rank,
           c.embedding <=> $3::vector as distance
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
                   ts_rank_cd(c.fts_tr, q.tr),
                   ts_rank_cd(c.fts_en, q.en)
               ) as score
        from chunks c
        join accessible a on a.id = c.document_id
        cross join q
        where c.fts_tr @@ q.tr or c.fts_en @@ q.en
    ) ranked
    order by score desc, id
    limit $6
)
select c.id, c.content, c.content_type, c.page_start, c.page_end,
       c.section_path, c.bbox,
       v.rank as vector_rank, k.rank as keyword_rank,
       v.distance as vector_distance
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

    async def replace_page_lines(
        self,
        *,
        document_id: UUID,
        user_id: UUID,
        lines_by_page: dict[int, list[OcrLine]],
    ) -> int:
        """Write the line geometry for a document's OCR'd pages.

        Delete-then-insert for the same reason `replace_chunks` does it:
        ingestion is retryable (ADR 007), and a retry that appended would leave
        two boxes for every line, each drawn on top of the other.

        A document with a text layer calls this with nothing and gets a delete,
        which is correct — a re-ingest that no longer needs OCR should not leave
        the previous run's geometry behind.
        """
        rows = [
            (
                document_id,
                user_id,
                page,
                line.text,
                line.bbox.x0,
                line.bbox.top,
                line.bbox.x1,
                line.bbox.bottom,
            )
            for page, lines in sorted(lines_by_page.items())
            for line in lines
        ]

        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute("delete from page_lines where document_id = $1", document_id)
            if rows:
                await connection.executemany(
                    """
                    insert into page_lines (
                        document_id, user_id, page, content, x0, top, x1, bottom
                    ) values ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    rows,
                )

        if rows:
            log.info("page_lines_written", document_id=str(document_id), count=len(rows))
        return len(rows)

    # -------------------------------------------------------------------------
    # read
    # -------------------------------------------------------------------------

    async def page_lines(self, document_id: UUID, page: int) -> list[tuple[str, dict[str, float]]]:
        """Every OCR'd line on one page, in reading order.

        Ordered top-to-bottom then left-to-right so the client can merge
        adjacent runs without sorting them itself.
        """
        rows = await self._pool.fetch(
            """
            select content, x0, top, x1, bottom from page_lines
             where document_id = $1 and page = $2
             order by top, x0
            """,
            document_id,
            page,
        )
        return [
            (
                row["content"],
                {
                    "x0": float(row["x0"]),
                    "top": float(row["top"]),
                    "x1": float(row["x1"]),
                    "bottom": float(row["bottom"]),
                },
            )
            for row in rows
        ]

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

    async def all_chunks(
        self,
        *,
        document_id: UUID,
        user_id: UUID | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        """Every chunk of one document, in document order.

        This is the sweep that typed extraction runs on, and it is deliberately
        *not* a search: ordering by `ordinal` keeps a clause next to the table
        that qualifies it, which relevance ordering would separate. Nothing here
        scores anything, so the returned chunks carry no ranks.

        Access is checked in SQL with the same predicate as `hybrid_search` —
        samples are readable by anyone, everything else is owner-only. The
        service-role key bypasses RLS (see `0005_rls.sql`), so this WHERE clause
        is the actual guard, not a second line of defence.

        `limit` is required rather than defaulted. A caller that forgets it on a
        200-page policy gets an unbounded read into memory and an unbounded
        extraction bill; making it explicit means the ceiling is always a
        decision somebody made.
        """
        rows = await self._pool.fetch(
            """
            select c.id, c.content, c.content_type, c.page_start, c.page_end,
                   c.bbox, c.section_path
              from chunks c
              join documents d on d.id = c.document_id
             where c.document_id = $1
               and d.status = 'ready'
               and (d.is_sample or d.user_id = $2)
             order by c.ordinal
             limit $3
            """,
            document_id,
            user_id,
            limit,
        )
        return [_to_plain_chunk(row) for row in rows]

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


def _to_plain_chunk(row: Any) -> RetrievedChunk:
    """A chunk read directly rather than retrieved, so it has no ranks.

    Separate from `_to_chunk` because that one reads `vector_rank` and
    `keyword_rank`, columns only the hybrid query produces. Reusing it here
    would mean inventing two zeros and calling them ranks.
    """
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
    )


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
        vector_distance=(
            float(row["vector_distance"]) if row["vector_distance"] is not None else None
        ),
    )
