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
import re
import time
from collections import deque
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

# -----------------------------------------------------------------------------
# Rate limiting
# -----------------------------------------------------------------------------
# The quota counts **texts, not requests**, and that distinction is the whole
# reason this section exists.
#
# Batching hid it. A real 27-page policy chunks into 148 passages, which this
# client sends as 5 HTTP requests — comfortably under any per-request limit. The
# free tier rejected it anyway:
#
#   Quota exceeded for metric: embed_content_free_tier_requests, limit: 100
#
# 5 requests against a limit of 100 cannot exceed it; 148 texts can. So the unit
# to pace is the passage, and a single ordinary document is 1.5× the entire
# minute's allowance on its own. Before this, the first real document anyone
# uploaded failed — not a large one, an ordinary one.
#
# Paced rather than merely retried, because the two failures are different: a
# retry recovers from a limit somebody else tripped, while pacing stops us from
# tripping it ourselves. Ingestion runs in the background behind a progress
# indicator, so spending ninety seconds on a document nobody is watching is a
# far better outcome than failing it in ten.
EMBED_TEXTS_PER_MINUTE = 100
RATE_WINDOW_SECONDS = 60.0

# Retries are for the limit we did not cause. More attempts than before and a
# longer ceiling, because a quota window is a minute wide and the old schedule
# (1.5s, 3s, 6s) gave up after ten seconds against a provider that had just
# replied "retry in 58s".
MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 65.0

# `'retryDelay': '58s'` in the error detail, or `Please retry in 1.23s` in its
# message. The provider knows exactly how long its own window has left, and
# guessing when it has already said so is how the old backoff got this wrong.
_RETRY_AFTER = re.compile(r"retry(?:Delay|\s+in)['\":\s]+(\d+(?:\.\d+)?)s", re.IGNORECASE)


def _retry_after(error: Exception) -> float | None:
    match = _RETRY_AFTER.search(str(error))
    if not match:
        return None
    return min(float(match.group(1)), MAX_BACKOFF_SECONDS)


# The free tier has two ceilings and they need different words. A per-minute
# limit clears on its own within a minute; a per-day one does not clear until
# the next day, and telling somebody to "try again in a few minutes" then is
# advice that cannot work — they will retry, fail, and have no idea why.
_DAILY_QUOTA = re.compile(r"PerDay|per\s*day", re.IGNORECASE)


def is_daily_quota(error: Exception) -> bool:
    """Whether this failure is the daily allowance rather than the per-minute one.

    Observed as `quotaId: EmbedContentRequestsPerDayPerProjectPerModel-FreeTier`
    while ingesting a real 148-chunk policy. Pacing cannot help with this one —
    it is a wall, not a window, and the only fixes are waiting for tomorrow or
    enabling billing.
    """
    return bool(_DAILY_QUOTA.search(str(error)))


class _RateWindow:
    """A sliding window over the texts sent in the last minute.

    Per process, which is the honest scope: on a scale-to-zero deployment each
    instance keeps its own count, so two instances ingesting at once can still
    exceed the quota between them. That case ends in a 429 and the retry below
    handles it. What this prevents is the guaranteed failure — one document,
    one instance, over the limit by itself.
    """

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._sent: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> int:
        while self._sent and now - self._sent[0][0] >= RATE_WINDOW_SECONDS:
            self._sent.popleft()
        return sum(count for _, count in self._sent)

    async def reserve(self, count: int) -> None:
        """Wait until `count` more texts fit, then record them as sent."""
        while True:
            now = time.monotonic()
            in_window = self._prune(now)
            if in_window + count <= self._limit or not self._sent:
                # `not self._sent` lets a batch larger than the whole limit
                # through rather than blocking forever. It will 429, and the
                # retry will carry it — a slow success beats a deadlock.
                self._sent.append((now, count))
                return
            wait = RATE_WINDOW_SECONDS - (now - self._sent[0][0])
            log.info("embedding_paced", waiting_seconds=round(wait, 1), in_window=in_window)
            await asyncio.sleep(max(wait, 0.1))


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
        texts_per_minute: int = EMBED_TEXTS_PER_MINUTE,
    ) -> None:
        self._client = build_client(api_key)
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._window = _RateWindow(texts_per_minute)
        self.total_tokens = 0

        # What this client has spent against the quota, for the life of the
        # process. `passages` is the number that matters: the free tier's
        # allowance is counted in them, not in HTTP requests, which is what a
        # 27-page policy discovered by being rejected as 148 of a possible 100.
        self.requests = 0
        self.passages = 0
        self.billable_characters = 0

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
            # Counted before the call, not after: a request that is in flight
            # has already spent its share of the quota.
            await self._window.reserve(len(texts))
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
                # The provider's own figure when it gave one. It knows how much
                # of its window is left and we do not.
                delay = _retry_after(exc) or min(
                    BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS
                )
                log.warning("embedding_retry", attempt=attempt, delay=delay, error=str(exc))
                await asyncio.sleep(delay)
        else:  # pragma: no cover - the loop always breaks or raises
            raise EmbeddingError(str(last_error))

        metadata = getattr(response, "metadata", None)
        if metadata is not None and metadata.billable_character_count:
            self.billable_characters += int(metadata.billable_character_count)
        self.requests += 1
        self.passages += len(texts)

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
            # What the provider says it billed, and what the quota counts. Not
            # converted to tokens and not priced: the endpoint reports
            # characters while the rate card is per token, and inventing the
            # ratio between them would be exactly the fabricated number
            # `api/pricing.py` exists to refuse. Reported so the cost of an
            # ingest is at least *visible* — a 27-page policy is 132 passages
            # against a free-tier allowance of 1,000 a day.
            billable_characters=self.billable_characters,
            passages_this_run=len(texts),
        )
        return out

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], EMBED_TASK_QUERY)
        return vectors[0]
