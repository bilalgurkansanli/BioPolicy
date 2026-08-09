"""Types shared by retrieval and generation.

`RetrievedChunk` is the join between the two halves of the system. Retrieval
produces it; context assembly stamps a `context_id` onto it; the model cites
that id; citation binding uses the id to find its way back to this exact object
and check the model's quote against `content`.

That round trip is the whole mechanism. It is why the model is never asked to
report a page number — a page number coming out of a model is unverifiable by
construction, whereas `[C3]` can be checked against what was actually put in
front of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from api.ingest.types import BBox


@dataclass(slots=True)
class RetrievedChunk:
    """A chunk that came back from search, with its provenance and scores."""

    chunk_id: UUID
    content: str
    content_type: str  # 'text' | 'table'
    page_start: int
    page_end: int
    section_path: str
    bbox: BBox | None = None

    # --- ranking ------------------------------------------------------------
    # Ranks are 1-based positions within each arm, or None when that arm did not
    # return this chunk at all. Kept separately rather than collapsed into one
    # number because the debug CLI and the eval need to show *why* something
    # ranked where it did.
    vector_rank: int | None = None
    keyword_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None

    # Cosine distance between the query and this chunk, straight out of pgvector
    # — 0 is identical, 1 is orthogonal. `None` when the keyword arm found this
    # chunk and the vector arm did not.
    #
    # Kept alongside the ranks rather than folded into them because it answers a
    # question ranks cannot: not "which chunk is best" but "is the best one any
    # good". The retrieval floor is built on this and could not be built on RRF.
    vector_distance: float | None = None

    # Assigned by context assembly. None until the chunk is actually placed in a
    # prompt — a chunk that was retrieved but trimmed away has no id, and a
    # citation naming it must therefore be dropped.
    context_id: str | None = None

    @property
    def page_label(self) -> str:
        if self.page_start == self.page_end:
            return f"page {self.page_start}"
        return f"pages {self.page_start}–{self.page_end}"
