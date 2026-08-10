"""The Voyage embedder.

Voyage limits by tokens per minute where Google limited by passages, so the
pacing here counts something different and the batching has to size by tokens
rather than by count. An account without a payment method gets 3 requests and
10K tokens a minute — the 27-page policy is ~36K tokens, so it succeeds in about
four minutes instead of failing in ten seconds.
"""

from __future__ import annotations

import asyncio

import pytest

from api.config import Settings
from api.deps import build_embedder, embedding_model
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.voyage_embedder import (
    DEFAULT_REQUESTS_PER_MINUTE,
    DEFAULT_TOKENS_PER_MINUTE,
    MAX_BATCH_TEXTS,
    MAX_BATCH_TOKENS,
    VoyageEmbedder,
    _batches,
    _RateWindow,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture(name="clock")
def clock_fixture(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    clock = _Clock()
    monkeypatch.setattr("api.retrieval.voyage_embedder.time.monotonic", clock.monotonic)
    monkeypatch.setattr(asyncio, "sleep", clock.sleep)
    return clock


# --- pacing -------------------------------------------------------------------


async def test_a_small_batch_does_not_wait(clock: _Clock) -> None:
    window = _RateWindow(requests_per_minute=3, tokens_per_minute=10_000)

    await window.reserve(2_000)

    assert clock.slept == []


async def test_the_token_ceiling_is_enforced(clock: _Clock) -> None:
    """The limit that actually bit: 36K tokens against 10K a minute."""
    window = _RateWindow(requests_per_minute=100, tokens_per_minute=10_000)

    await window.reserve(8_000)
    await window.reserve(8_000)

    assert sum(clock.slept) == pytest.approx(60.0, abs=1.0)


async def test_the_request_ceiling_is_enforced_too(clock: _Clock) -> None:
    """Either can bite first — many short passages exhaust requests, few long
    ones exhaust tokens."""
    window = _RateWindow(requests_per_minute=3, tokens_per_minute=1_000_000)

    for _ in range(4):
        await window.reserve(10)

    assert sum(clock.slept) == pytest.approx(60.0, abs=1.0)


async def test_an_oversized_batch_is_not_a_deadlock(clock: _Clock) -> None:
    """It will 429 and the retry carries it. Waiting for room that cannot exist
    would hang a background job forever."""
    window = _RateWindow(requests_per_minute=3, tokens_per_minute=1_000)

    await asyncio.wait_for(window.reserve(50_000), timeout=1)

    assert clock.slept == []


# --- batching -----------------------------------------------------------------


def test_batches_are_sized_by_tokens_not_by_count() -> None:
    """128 passages might be 3K tokens or 30K, and only one of those fits."""
    long_passage = "kelime " * 3_000

    batches = _batches([long_passage] * 6)

    assert len(batches) > 1
    for batch in batches:
        assert len(batch) <= MAX_BATCH_TEXTS


def test_short_passages_still_batch_together() -> None:
    batches = _batches(["kısa metin"] * 50)

    assert len(batches) == 1


def test_the_count_ceiling_still_applies() -> None:
    batches = _batches(["a"] * (MAX_BATCH_TEXTS * 2 + 5))

    assert all(len(batch) <= MAX_BATCH_TEXTS for batch in batches)


def test_every_passage_survives_batching() -> None:
    """The failure this guards is silent: a lost passage is a clause that can
    never be retrieved, and nothing downstream would report it."""
    texts = [f"madde {index}" for index in range(300)]

    assert [text for batch in _batches(texts) for text in batch] == texts


def test_a_single_passage_over_the_batch_ceiling_is_still_sent() -> None:
    """One chunk cannot be split here — it is already the smallest unit — so it
    goes on its own and the provider decides."""
    huge = "kelime " * (MAX_BATCH_TOKENS * 2)

    batches = _batches([huge])

    assert len(batches) == 1
    assert batches[0] == [huge]


# --- the ceiling is configuration, not a constant -----------------------------
#
# The pacing was written to be adjustable and then wired up so it wasn't: the
# constructor took both limits, `build_embedder` passed neither, and the
# defaults won every time. Nothing failed — a deployment that had lifted its
# ceiling with the provider simply went on embedding at 10K tokens a minute, and
# the only symptom was an ingest that stayed four minutes long for no visible
# reason. These pin the wiring rather than the numbers.


def _settings(**overrides: object) -> Settings:
    return Settings(app_env="development", _env_file=None, **overrides)  # type: ignore[arg-type]


def test_the_configured_ceiling_reaches_the_embedder() -> None:
    embedder = build_embedder(
        _settings(
            voyage_api_key="pa-test",
            voyage_requests_per_minute=2_000,
            voyage_tokens_per_minute=16_000_000,
        )
    )

    assert isinstance(embedder, VoyageEmbedder)
    assert embedder.rate_limits == (2_000, 16_000_000)


def test_an_unconfigured_deployment_gets_the_reduced_tier() -> None:
    """What an account with no payment method on file is actually held at, so a
    fresh clone paces itself to the limit it really has."""
    embedder = build_embedder(_settings(voyage_api_key="pa-test"))

    assert isinstance(embedder, VoyageEmbedder)
    assert embedder.rate_limits == (DEFAULT_REQUESTS_PER_MINUTE, DEFAULT_TOKENS_PER_MINUTE)


def test_without_a_key_the_provider_is_gemini_not_a_misconfigured_voyage() -> None:
    """The fallback still exists, and picking it must not depend on the limits."""
    embedder = build_embedder(_settings(voyage_api_key=None, google_api_key="test"))

    assert isinstance(embedder, GeminiEmbedder)


# --- naming a provider without building one -----------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"voyage_api_key": "pa-test"},
        {"voyage_api_key": None, "google_api_key": "test"},
    ],
    ids=["voyage", "gemini-fallback"],
)
def test_the_name_matches_what_gets_built(overrides: dict[str, object]) -> None:
    """Two functions answering the same question have to keep agreeing."""
    settings = _settings(**overrides)

    assert embedding_model(settings) == build_embedder(settings).model


def test_naming_the_model_works_with_nothing_configured() -> None:
    """`/api/health` asks this on an unconfigured deployment, unauthenticated.

    Building an embedder to read the name raised `ValueError` from the genai
    client, so the one route whose job is to say what is missing answered 500 on
    precisely the deployment that needed it.
    """
    settings = _settings(voyage_api_key=None, google_api_key=None)

    assert embedding_model(settings) == settings.gemini_embedding_model
    with pytest.raises(ValueError):
        build_embedder(settings)  # the reason the helper exists
