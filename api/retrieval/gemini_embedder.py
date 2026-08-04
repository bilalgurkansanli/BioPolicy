"""Gemini embeddings at 1536 dimensions — the concrete side of constraint C3.

Two things make this file more than an SDK wrapper.

**`output_dimensionality` is requested explicitly, every time.** The model's
native width is 3072, and pgvector's HNSW index tops out at 2000. A vector that
arrives at full width does not raise a helpful error — it is rejected by the
`vector(1536)` column at insert time, which is the *good* outcome. The bad
outcome is a code path that silently drops the parameter and starts producing
vectors of a different width than everything already stored, at which point the
distances are arithmetic performed on unrelated numbers. `validate_dimensions`
runs on every response so that failure is caught at the boundary.

**Document and query embeddings use different task types.** Gemini embeds
asymmetrically. Passing `RETRIEVAL_DOCUMENT` for a question raises nothing and
silently costs recall, so the two are separate methods rather than one method
with a flag someone can pass wrongly.

The returned vectors are re-normalised after truncation. Under cosine distance —
what migration 0003 indexes with — this changes no ranking, since cosine divides
by magnitude anyway. It is done because a truncated Matryoshka prefix is no
longer unit-length, and if the index metric is ever changed to inner product
that difference stops being cosmetic and starts being a silent ranking bug.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, cast

from google.genai import types as genai_types

from api.constants import (
    EMBED_TASK_DOCUMENT,
    EMBED_TASK_QUERY,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
)
from api.gemini_client import build_client
from api.logging_config import get_logger
from api.retrieval.embedder import EmbeddingError, validate_dimensions

log = get_logger(__name__)

# Gemini's embedding endpoint is rate-limited per minute. A 200-page document
# produces enough batches to trip it, so retries back off rather than hammering.
MAX_ATTEMPTS = 4
BASE_BACKOFF_SECONDS = 1.5


def _normalise(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        raise EmbeddingError("provider returned a zero vector")
    return [v / magnitude for v in vector]


class GeminiEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        dimensions: int = EMBEDDING_DIM,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> None:
        self._client = build_client(api_key)
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self.total_tokens = 0

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        config = genai_types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self._dimensions,
        )

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.aio.models.embed_content(
                    model=self._model,
                    # list invariance: list[str] is not list[str | Part | ...]
                    contents=cast(Any, list(texts)),
                    config=config,
                )
                break
            except Exception as exc:  # the SDK raises broadly
                last_error = exc
                if attempt == MAX_ATTEMPTS:
                    raise EmbeddingError(
                        f"embedding failed after {MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc
                delay = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                log.warning("embedding_retry", attempt=attempt, delay=delay, error=str(exc))
                await asyncio.sleep(delay)
        else:  # pragma: no cover - the loop always breaks or raises
            raise EmbeddingError(str(last_error))

        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"asked for {len(texts)} embeddings, received {len(embeddings)} — "
                "refusing to write vectors that do not line up with their text"
            )

        vectors = [list(e.values or []) for e in embeddings]
        validate_dimensions(vectors, expected=self._dimensions)
        return [_normalise(v) for v in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage, in batches, preserving input order."""
        if not texts:
            return []

        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            out.extend(await self._embed(batch, EMBED_TASK_DOCUMENT))

        log.info(
            "documents_embedded",
            count=len(out),
            dimensions=self._dimensions,
            batches=math.ceil(len(texts) / self._batch_size),
        )
        return out

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], EMBED_TASK_QUERY)
        return vectors[0]
