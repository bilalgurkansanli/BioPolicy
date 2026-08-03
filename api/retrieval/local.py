"""An in-memory `ChunkSearcher` for offline development.

## What this is for, and what it is not

This exists so the whole pipeline — parse, chunk, retrieve, fuse, assemble — can
be run and inspected on a real PDF with no database, no API key and no spend. It
is a **plumbing** check. Given a question you can see which chunks come back,
whether the coverage table survived, whether the section paths look right, and
exactly what text would have gone into the prompt.

It is **not** a retrieval-quality check, and reading it as one would be a
mistake worth avoiding. It has no embeddings: the "vector" arm is BM25-ish
lexical scoring wearing a vector arm's hat. It therefore cannot find `su
baskını` from `sel`, which is the single most important thing the real vector
arm does. Retrieval quality is measured in Phase 5, against real embeddings,
with numbers published.

Kept out of the request path entirely — nothing under `api/routers` imports it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from api.constants import KEYWORD_CANDIDATES, VECTOR_CANDIDATES
from api.ingest.chunker import Chunk
from api.retrieval.types import RetrievedChunk

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenise(text: str) -> list[str]:
    """Lowercase word tokens.

    `casefold` rather than `lower` for Unicode correctness. Turkish dotted and
    dotless I do not fold the way a Turkish speaker expects, but both the
    document and the query go through the same function, so the two sides agree
    — which is all a lexical match needs.
    """
    return [m.group(0).casefold() for m in _TOKEN.finditer(text)]


@dataclass(slots=True)
class _Indexed:
    chunk: RetrievedChunk
    counts: Counter[str]
    length: int


@dataclass(slots=True)
class InMemoryStore:
    """Lexical-only stand-in for `ChunkStore`."""

    entries: list[_Indexed] = field(default_factory=list)
    document_frequency: Counter[str] = field(default_factory=Counter)

    @classmethod
    def from_chunks(cls, chunks: list[Chunk], document_id: UUID | None = None) -> InMemoryStore:
        del document_id  # single-document by construction; kept for signature parity
        store = cls()
        for chunk in chunks:
            tokens = tokenise(chunk.embed_text)
            counts = Counter(tokens)
            store.entries.append(
                _Indexed(
                    chunk=RetrievedChunk(
                        chunk_id=uuid4(),
                        content=chunk.content,
                        content_type=chunk.content_type,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        section_path=chunk.section_path,
                        bbox=chunk.bbox,
                    ),
                    counts=counts,
                    length=len(tokens),
                )
            )
            for term in set(counts):
                store.document_frequency[term] += 1
        return store

    def _score(self, query_tokens: list[str], entry: _Indexed) -> float:
        """TF-IDF cosine-ish. Deliberately unsophisticated."""
        total = len(self.entries) or 1
        score = 0.0
        for term in set(query_tokens):
            tf = entry.counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + total / (1 + self.document_frequency[term]))
            score += (tf / (entry.length or 1)) * idf
        return score

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
        del document_id, user_id, query_embedding  # no access control offline
        tokens = tokenise(query_text)

        scored = [(self._score(tokens, e), e) for e in self.entries]
        scored = [(s, e) for s, e in scored if s > 0]
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunk.page_start))

        results: list[RetrievedChunk] = []
        for rank, (_, entry) in enumerate(scored[: max(vector_limit, keyword_limit)], start=1):
            chunk = entry.chunk
            # Both ranks are set from the same ordering, which is exactly why
            # this cannot stand in for a quality measurement — the two arms are
            # not independent here, and RRF's whole value is that they are.
            chunk.vector_rank = rank if rank <= vector_limit else None
            chunk.keyword_rank = rank if rank <= keyword_limit else None
            results.append(chunk)
        return results


class NullEmbedder:
    """Returns nothing useful, because the local store ignores embeddings."""

    name = "null-embedder"
    model = "none"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.0]
