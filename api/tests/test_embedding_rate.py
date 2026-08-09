"""Staying inside the embedding quota.

The first real document anyone uploaded failed here, and it was not a large one:
a 27-page home policy, 148 chunks, sent as 5 HTTP requests. Google's free tier
rejected it with

    Quota exceeded for metric: embed_content_free_tier_requests, limit: 100

Five requests cannot exceed a limit of 100. One hundred and forty-eight texts
can — the quota counts passages, and batching hid that completely. So an
ordinary document was 1.5× the whole minute's allowance by itself, and every
upload of a real policy was going to fail.
"""

from __future__ import annotations

import asyncio

import pytest

from api.retrieval.gemini_embedder import (
    MAX_BACKOFF_SECONDS,
    _RateWindow,
    _retry_after,
    is_daily_quota,
)


class _Clock:
    """A monotonic clock the test moves by hand.

    `asyncio.sleep` is patched to advance it rather than to wait, so a test
    about a sixty-second window runs in microseconds and asserts on the time
    that *would* have passed.
    """

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
    monkeypatch.setattr("api.retrieval.gemini_embedder.time.monotonic", clock.monotonic)
    monkeypatch.setattr(asyncio, "sleep", clock.sleep)
    return clock


# --- the window ---------------------------------------------------------------


async def test_a_batch_within_the_limit_does_not_wait(clock: _Clock) -> None:
    window = _RateWindow(100)

    await window.reserve(32)

    assert clock.slept == []


async def test_the_real_document_is_paced_instead_of_failing(clock: _Clock) -> None:
    """148 texts against a limit of 100, in batches of 32 — the exact shape of
    the upload that failed. It must finish, and it must take about a minute."""
    window = _RateWindow(100)
    remaining = 148

    while remaining > 0:
        batch = min(32, remaining)
        await window.reserve(batch)
        remaining -= batch

    assert sum(clock.slept) == pytest.approx(60.0, abs=1.0)


async def test_the_window_slides_rather_than_resetting(clock: _Clock) -> None:
    """A fixed window would let 100 through at 59s and 100 more at 61s."""
    window = _RateWindow(100)
    await window.reserve(100)

    clock.now += 30.0
    await window.reserve(50)

    # The first 100 are still inside the minute, so this had to wait for them
    # to age out rather than starting a fresh allowance.
    assert sum(clock.slept) == pytest.approx(30.0, abs=0.5)


async def test_a_batch_larger_than_the_whole_limit_is_not_a_deadlock(
    clock: _Clock,
) -> None:
    """It will 429 and the retry carries it. A slow success beats a hang, and a
    hang is what waiting for room that can never exist would produce."""
    window = _RateWindow(10)

    await asyncio.wait_for(window.reserve(64), timeout=1)

    assert clock.slept == []


async def test_reserving_counts_before_the_call_not_after(clock: _Clock) -> None:
    """A request in flight has already spent its share of the quota."""
    window = _RateWindow(100)

    await window.reserve(60)
    await window.reserve(60)

    assert sum(clock.slept) > 0


# --- listening to the provider ------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "429 RESOURCE_EXHAUSTED {'retryDelay': '58s'}",
        "Quota exceeded. Please retry in 58.5s",
        "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '58s'}",
    ],
)
def test_the_providers_own_delay_is_used_when_it_gives_one(message: str) -> None:
    """It knows how much of its window is left; we do not.

    The old schedule was 1.5s, 3s, 6s — it gave up after ten seconds against a
    provider that had just replied "retry in 58s", which is how a recoverable
    rate limit became a failed upload.
    """
    delay = _retry_after(RuntimeError(message))

    assert delay is not None
    assert delay >= 58.0


def test_an_absurd_delay_is_capped() -> None:
    """A provider asking for an hour must not hold a background task for one."""
    assert _retry_after(RuntimeError("retryDelay: '3600s'")) == MAX_BACKOFF_SECONDS


def test_an_error_without_a_delay_falls_back_to_backoff() -> None:
    assert _retry_after(RuntimeError("500 internal error")) is None


# --- the two ceilings ---------------------------------------------------------


def test_the_daily_quota_is_told_apart_from_the_per_minute_one() -> None:
    """They need different advice. Pacing fixes the minute; nothing fixes the
    day except waiting for it, and "try again in a few minutes" then sends
    somebody into a retry loop that cannot succeed.

    Both were hit while ingesting one real policy.
    """
    daily = RuntimeError(
        "429 RESOURCE_EXHAUSTED quotaId: 'EmbedContentRequestsPerDayPerProjectPerModel-FreeTier'"
    )
    per_minute = RuntimeError(
        "429 RESOURCE_EXHAUSTED quotaId: "
        "'EmbedContentRequestsPerMinutePerUserPerProjectPerModel-FreeTier'"
    )

    assert is_daily_quota(daily) is True
    assert is_daily_quota(per_minute) is False


def test_an_unrelated_failure_is_not_read_as_a_daily_quota() -> None:
    assert is_daily_quota(RuntimeError("503 backend unavailable")) is False
