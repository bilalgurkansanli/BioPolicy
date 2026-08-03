"""Reciprocal Rank Fusion.

## Why fuse at all

Policy questions mix two incompatible kinds of matching, often inside one
sentence. "Sel hasarı kapsanıyor mu, muafiyeti ne kadar?" is semantic in its
first half and lexical in its second — and the lexical half is where the money
is. Pure vector search reliably misses exact tokens: a policy number, `Madde
7.3`, `TL 250.000`. Embeddings map those onto a diffuse region of the space
because they carry almost no distributional meaning, which is precisely why they
are useful identifiers.

Keyword search finds them instantly and is helpless at "does this cover
flooding?" when the document says "su baskını".

## Why RRF and not a weighted score

The two arms produce scores on scales that have no relationship to each other. A
cosine distance of 0.23 and a `ts_rank_cd` of 0.089 are not comparable, are not
comparable *even after normalising*, and their distributions shift per query and
per document. Any `alpha * vector + (1 - alpha) * keyword` requires an alpha
tuned on data we do not have, and it silently re-tunes itself every time a
document's length distribution changes.

RRF throws the scores away and keeps only the ranks:

    score(d) = sum over arms of  1 / (k + rank(d, arm))

Ranks are comparable by construction. A chunk at rank 3 in both arms can outrank
one at rank 1 in only one arm — which is exactly the behaviour we want when the
two arms disagree, because agreement across two independent retrieval methods is
real evidence and a single arm's confidence is not.

`k = 60` is from the original RRF paper and is the near-universal default. It is
not tuned here, and tuning it would need far more evaluation data than 40 golden
questions can provide.
"""

from __future__ import annotations

from collections.abc import Iterable

from api.constants import RRF_K
from api.retrieval.types import RetrievedChunk


def fuse(
    chunks: Iterable[RetrievedChunk],
    *,
    k: int = RRF_K,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Score and order chunks that already carry their per-arm ranks.

    This is the path the live retriever takes: the hybrid SQL computes both
    ranks in one round trip, so there is nothing left to merge — only to score.
    A chunk absent from an arm has `None` for that rank and simply contributes
    nothing from it.
    """
    scored = list(chunks)
    for chunk in scored:
        score = 0.0
        if chunk.vector_rank is not None:
            score += 1.0 / (k + chunk.vector_rank)
        if chunk.keyword_rank is not None:
            score += 1.0 / (k + chunk.keyword_rank)
        chunk.rrf_score = score

    scored.sort(
        # Ties break on document order rather than on whatever order the rows
        # arrived in, so the same query ranks identically every time. A
        # retrieval metric computed over a non-deterministic ordering is noise.
        key=lambda c: (-c.rrf_score, c.page_start, str(c.chunk_id))
    )
    return scored[:limit] if limit is not None else scored


def reciprocal_rank_fusion(
    vector_hits: list[RetrievedChunk],
    keyword_hits: list[RetrievedChunk],
    *,
    k: int = RRF_K,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse two separately-ranked lists.

    Position in each input list *is* the rank. Used where the two arms genuinely
    arrive separately — the eval harness comparing arms in isolation, and the
    tests. Delegates the scoring to `fuse` so both paths cannot diverge.
    """
    merged: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_hits, start=1):
        chunk.vector_rank = rank
        merged[str(chunk.chunk_id)] = chunk

    for rank, chunk in enumerate(keyword_hits, start=1):
        key = str(chunk.chunk_id)
        target = merged.setdefault(key, chunk)
        target.keyword_rank = rank

    return fuse(merged.values(), k=k, limit=limit)
