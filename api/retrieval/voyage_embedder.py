"""Voyage embeddings — the vector side, after Google's free tier ran out of room.

## Why a third provider

Anthropic has no embedding endpoint. Its client exposes `messages`,
`completions` and `models`, and its own documentation points at Voyage for
vectors, so "use the model we already pay for" is not available: producing an
embedding and producing an answer are different services.

Google's was the first choice and worked. What ended it was not price but a
quota shape: the free tier counts *passages*, 1,000 a day, and a real 27-page
policy is 132 of them. Seven documents a day is not a demo. Voyage's free
allowance is 200M tokens — the same policy is 36K — and past that it is
$0.02 per million against Google's $0.15.

## Two things this gets right that the Gemini client could not

**Token counts come from the provider.** Voyage returns `usage.total_tokens`,
so an ingest can finally be priced and recorded. Gemini's embedding endpoint
reports `billable_character_count` while its rate card is per token, and the
ratio between them is not something this project is willing to invent — which
is why embedding spend was invisible to the budget breaker until now.

**Vectors arrive unit-length.** No renormalisation, so there is no step that
could quietly change ranking if the index metric were ever changed.

## No new dependency

Plain HTTP through `httpx`, which is already here. The official SDK would add a
package to a project that keeps its dependency list short and licence-checked
(ADR 002), for an endpoint that takes three fields.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections import deque
from typing import Any

import httpx

from api.constants import EMBEDDING_DIM
from api.ingest.chunker import count_tokens
from api.logging_config import get_logger
from api.retrieval.embedder import EmbeddingError, validate_dimensions

log = get_logger(__name__)

ENDPOINT = "https://api.voyageai.com/v1/embeddings"

# -----------------------------------------------------------------------------
# Rate limiting
# -----------------------------------------------------------------------------
# Voyage limits by **tokens per minute**, where Google limited by passages, and
# an account without a payment method on file gets a small allowance:
#
#   You have not yet added your payment method ... reduced rate limits
#   of 3 RPM and 10K TPM
#
# The 27-page policy is ~36K tokens — measured, not estimated — so 3.6 of the
# four minutes it takes to ingest are spent waiting on this ceiling and nothing
# else. Adding a payment method lifts it without spending anything: the first
# 200M tokens are free either way, and this document is 36K of them.
#
# These are defaults, not the policy. `VOYAGE_REQUESTS_PER_MINUTE` and
# `VOYAGE_TOKENS_PER_MINUTE` override them, and a deployment that has lifted its
# ceiling with the provider must raise them here too: the limit is enforced on
# both sides, and the slower one wins. They are set to the reduced tier because
# that is what an account with no payment method actually gets, and pacing
# faster than the server allows converts progress into 429s and backoff.
#
# Batches are sized by tokens rather than by count for the same reason: 128
# passages might be 3K tokens or 30K, and only one of those fits.
DEFAULT_TOKENS_PER_MINUTE = 10_000
DEFAULT_REQUESTS_PER_MINUTE = 3
RATE_WINDOW_SECONDS = 60.0

# Kept under the per-minute token ceiling so a single batch can never be
# unsendable. The API itself accepts 1,000 texts and 1M tokens per request.
MAX_BATCH_TOKENS = 8_000
MAX_BATCH_TEXTS = 128

TIMEOUT_SECONDS = 60.0

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 65.0

# The two `input_type` values. Voyage prepends a different instruction to each,
# which is the same asymmetry Gemini's task types express: a question and the
# passage answering it are not the same kind of text, and embedding one as the
# other silently costs recall.
INPUT_DOCUMENT = "document"
INPUT_QUERY = "query"

_RETRY_AFTER = re.compile(r"retry[- ]?after['\":\s]+(\d+(?:\.\d+)?)", re.IGNORECASE)


class _RateWindow:
    """A sliding minute, counting both requests and tokens.

    Two ceilings rather than one, because Voyage enforces both and either can
    bite first: a document of many short passages runs out of requests, a
    document of few long ones runs out of tokens.
    """

    def __init__(self, *, requests_per_minute: int, tokens_per_minute: int) -> None:
        self._requests_limit = requests_per_minute
        self._tokens_limit = tokens_per_minute
        self._sent: deque[tuple[float, int]] = deque()

    @property
    def limits(self) -> tuple[int, int]:
        return self._requests_limit, self._tokens_limit

    def _prune(self, now: float) -> tuple[int, int]:
        while self._sent and now - self._sent[0][0] >= RATE_WINDOW_SECONDS:
            self._sent.popleft()
        return len(self._sent), sum(tokens for _, tokens in self._sent)

    async def reserve(self, tokens: int) -> None:
        while True:
            now = time.monotonic()
            requests, spent = self._prune(now)
            fits = requests + 1 <= self._requests_limit and spent + tokens <= self._tokens_limit
            if fits or not self._sent:
                # `not self._sent` lets an oversized batch through rather than
                # waiting for room that will never exist. It will 429 and the
                # retry carries it; a slow success beats a deadlock.
                self._sent.append((now, tokens))
                return
            wait = RATE_WINDOW_SECONDS - (now - self._sent[0][0])
            log.info(
                "embedding_paced",
                provider="voyage",
                waiting_seconds=round(wait, 1),
                requests_in_window=requests,
                tokens_in_window=spent,
            )
            await asyncio.sleep(max(wait, 0.1))


def _batches(texts: list[str]) -> list[list[str]]:
    """Split by token budget first, count second.

    Estimated with the project's own tokenizer rather than Voyage's, which is
    not published. It is a yardstick for staying under a ceiling, not an
    accounting figure — `usage.total_tokens` from the response is what gets
    recorded — so a margin matters more than precision, and the batch ceiling is
    well under the per-minute one.
    """
    out: list[list[str]] = []
    current: list[str] = []
    budget = 0
    for text in texts:
        tokens = count_tokens(text)
        if current and (budget + tokens > MAX_BATCH_TOKENS or len(current) >= MAX_BATCH_TEXTS):
            out.append(current)
            current, budget = [], 0
        current.append(text)
        budget += tokens
    if current:
        out.append(current)
    return out


class VoyageEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        dimensions: int = EMBEDDING_DIM,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        tokens_per_minute: int = DEFAULT_TOKENS_PER_MINUTE,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._window = _RateWindow(
            requests_per_minute=requests_per_minute,
            tokens_per_minute=tokens_per_minute,
        )

        # What has been spent, for the life of the process. Unlike the Gemini
        # client's, `tokens` here is the provider's own figure.
        self.requests = 0
        self.passages = 0
        self.total_tokens = 0

    @property
    def name(self) -> str:
        return "voyage"

    @property
    def model(self) -> str:
        return self._model

    @property
    def rate_limits(self) -> tuple[int, int]:
        """The ceiling in force, as (requests, tokens) per minute.

        Worth being able to read from outside: the pacing is the single largest
        term in how long an ingest takes, and which numbers are in force is
        otherwise invisible — an operator who lifted the limit with the provider
        has no way to tell whether this process noticed.
        """
        return self._window.limits

    async def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingError("VOYAGE_API_KEY is not set.")

        payload: dict[str, Any] = {
            "input": texts,
            "model": self._model,
            "input_type": input_type,
            "output_dimension": self._dimensions,
        }

        estimated = sum(count_tokens(text) for text in texts)

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Reserved before the call: a request in flight has already spent
            # its share of the minute.
            await self._window.reserve(estimated)
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        ENDPOINT,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise EmbeddingError(f"HTTP {response.status_code}: {response.text[:200]}")
                if response.status_code != 200:
                    # 4xx other than rate limiting is a request this code got
                    # wrong; retrying it would just be slower.
                    raise EmbeddingError(
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    ) from None
                body = response.json()
                break
            except EmbeddingError as exc:
                last_error = exc
                if "HTTP 4" in str(exc) and "HTTP 429" not in str(exc):
                    raise
                if attempt == MAX_ATTEMPTS:
                    raise EmbeddingError(
                        f"embedding failed after {MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(_backoff(exc, attempt))
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == MAX_ATTEMPTS:
                    raise EmbeddingError(
                        f"embedding failed after {MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(_backoff(exc, attempt))
        else:  # pragma: no cover - the loop always breaks or raises
            raise EmbeddingError(str(last_error))

        data = body.get("data") or []
        if len(data) != len(texts):
            raise EmbeddingError(
                f"asked for {len(texts)} embeddings, received {len(data)} — "
                "refusing to write vectors that do not line up with their text"
            )

        # Returned in request order per the API contract, but sorted by the
        # index the response carries rather than trusted: a silent reordering
        # would attach every vector to the wrong passage, and nothing
        # downstream could detect it.
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors = [list(item["embedding"]) for item in ordered]
        validate_dimensions(vectors, expected=self._dimensions)

        self.requests += 1
        self.passages += len(texts)
        self.total_tokens += int((body.get("usage") or {}).get("total_tokens") or 0)

        return [_ensure_unit(vector) for vector in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage, in batches, preserving input order."""
        if not texts:
            return []

        out: list[list[float]] = []
        for batch in _batches(texts):
            out.extend(await self._embed(batch, INPUT_DOCUMENT))

        log.info(
            "documents_embedded",
            provider=self.name,
            count=len(out),
            dimensions=self._dimensions,
            tokens=self.total_tokens,
        )
        return out

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], INPUT_QUERY)
        return vectors[0]


def _backoff(error: Exception, attempt: int) -> float:
    """The provider's own figure when it gives one, else exponential."""
    match = _RETRY_AFTER.search(str(error))
    if match:
        return min(float(match.group(1)), MAX_BACKOFF_SECONDS)
    return float(min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS))


def _ensure_unit(vector: list[float]) -> list[float]:
    """Voyage returns unit-length vectors; this only catches it if that changes.

    Cosine distance divides by magnitude, so a non-unit vector would rank
    identically today — and would start ranking differently the day migration
    0003's index metric is changed to inner product. Cheap to keep honest.
    """
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise EmbeddingError("provider returned a zero vector")
    if abs(magnitude - 1.0) < 1e-6:
        return vector
    return [value / magnitude for value in vector]
