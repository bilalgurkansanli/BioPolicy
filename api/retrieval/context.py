"""Context assembly.

Turns ranked chunks into the block of text the model sees, and hands back the
mapping needed to verify what it says afterwards.

Two decisions here carry the product's central guarantee.

**Stable, opaque ids.** Each chunk is labelled `[C1]`, `[C2]`, … and the model
is required to cite by those labels. The alternative — letting it cite page
numbers — produces citations that cannot be checked: a page number in a model's
output is a claim about the document, not a pointer into what we retrieved. A
`[C3]` either matches a chunk we put in the prompt or it does not, and that is
decidable in one dictionary lookup.

**A hard token ceiling.** Chunks are added until the budget is spent, and the
rest are dropped. A chunk that gets dropped has no `context_id`, so a citation
naming it fails binding — which is the correct outcome, not a bug. The model
cannot cite what it was never shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.constants import CONTEXT_CHUNK_COUNT
from api.ingest.chunker import count_tokens
from api.retrieval.types import RetrievedChunk

# Ceiling on the assembled context. Chosen so that context + conversation
# history + the answer stay well inside the model's window, and — more
# importantly for a $30 budget — so that a single question has a knowable
# maximum cost.
MAX_CONTEXT_TOKENS = 6000


@dataclass(slots=True)
class AssembledContext:
    text: str
    """The block that goes into the prompt."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    """Only the chunks that actually made it in, in presentation order."""

    dropped: list[RetrievedChunk] = field(default_factory=list)
    """Retrieved but trimmed for budget. Never citable."""

    token_count: int = 0

    @property
    def by_id(self) -> dict[str, RetrievedChunk]:
        """Lookup used by citation binding. Only ever contains included chunks."""
        return {c.context_id: c for c in self.chunks if c.context_id is not None}

    @property
    def is_empty(self) -> bool:
        return not self.chunks


def assemble(
    chunks: list[RetrievedChunk],
    *,
    max_chunks: int = CONTEXT_CHUNK_COUNT,
    max_tokens: int = MAX_CONTEXT_TOKENS,
) -> AssembledContext:
    """Build the prompt context from ranked chunks, best first.

    Mutates each included chunk's `context_id`. Chunks that do not fit are
    returned in `dropped` with `context_id` left as None.
    """
    included: list[RetrievedChunk] = []
    dropped: list[RetrievedChunk] = []
    parts: list[str] = []
    total = 0

    for chunk in chunks:
        if len(included) >= max_chunks:
            chunk.context_id = None
            dropped.append(chunk)
            continue

        candidate_id = f"C{len(included) + 1}"
        rendered = _render(chunk, candidate_id)
        cost = count_tokens(rendered)

        # Always admit the first chunk, even if it alone exceeds the budget. An
        # oversized coverage table is exactly the chunk most likely to hold the
        # answer; returning an empty context because the best result was large
        # would be the worst possible trade.
        if included and total + cost > max_tokens:
            chunk.context_id = None
            dropped.append(chunk)
            continue

        chunk.context_id = candidate_id
        included.append(chunk)
        parts.append(rendered)
        total += cost

    return AssembledContext(
        text="\n\n".join(parts),
        chunks=included,
        dropped=dropped,
        token_count=total,
    )


def _render(chunk: RetrievedChunk, context_id: str) -> str:
    """One chunk, with its id and provenance on the header line.

    The section path is shown to the model because "Madde 4 > 4.7" tells it that
    a clause is an *exclusion*, which is frequently the difference between a
    correct "no" and a confident "yes". The page number is shown so the model
    can mention it in prose — but the citation itself is still bound by id, so a
    wrong page number in the answer text cannot corrupt the link.
    """
    location = chunk.page_label
    if chunk.section_path:
        location += f', "{chunk.section_path}"'

    kind = " (table)" if chunk.content_type == "table" else ""
    return f"[{context_id}] ({location}){kind}\n{chunk.content}"
