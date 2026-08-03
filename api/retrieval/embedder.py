"""Embedding provider interface.

The two things that must never drift apart are enforced here rather than left to
call sites:

**Dimensionality.** Every vector — document and query alike — must be exactly
`EMBEDDING_DIM`. A provider silently returning its native 3072 would produce
vectors Postgres rejects at insert time, which is the good case; the bad case is
a provider returning a *shorter* vector that pgvector accepts into a differently
sized column somewhere and yields meaningless distances.

**Task type.** Gemini embeds asymmetrically: a passage and a question about that
passage are different kinds of text, and telling the model which one it is at
encode time measurably improves retrieval. Getting this backwards — embedding
documents as queries — produces no error anywhere and silently degrades recall,
so it is a separate method rather than a flag someone can pass wrongly.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from api.constants import EMBEDDING_DIM


class EmbeddingError(RuntimeError):
    """The provider failed, or returned something unusable."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage. Order of the result matches the input."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a question for search."""
        ...


def validate_dimensions(vectors: list[list[float]], *, expected: int = EMBEDDING_DIM) -> None:
    """Fail loudly on a wrong-width vector, naming what was actually received.

    Called by every provider implementation before returning. A dimension
    mismatch that reaches the database surfaces as an opaque Postgres error
    hundreds of lines from its cause.
    """
    for index, vector in enumerate(vectors):
        if len(vector) != expected:
            raise EmbeddingError(
                f"Embedding {index} has {len(vector)} dimensions, expected {expected}. "
                "Check that output_dimensionality is being requested — the model's "
                "default is wider than pgvector's HNSW index can handle."
            )
