"""The answer cache.

Two properties matter more than the hit rate, and both are here: a cached answer
is never presented as a fresh one, and a private document is never cached at all.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest

from api.answer_cache import MAX_AGE_HOURS, AnswerCache, fingerprint, is_cacheable
from api.tests.fakes import FakePool

_ANY_ID = uuid4()


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "answer": "Deprem teminatının limiti 1.800.000 TL.",
        "refused": False,
        "suppressed": False,
        "citations": [{"context_id": "C1", "quote": "…"}],
    }
    payload.update(overrides)
    return payload


# --- the key ------------------------------------------------------------------


def test_the_same_question_typed_differently_is_one_key() -> None:
    """Case and spacing are noise; the cache should not miss on them."""
    assert fingerprint("Deprem limiti nedir?", "tr") == fingerprint(
        "  deprem   LİMİTİ nedir?  ".replace("İ", "i"), "tr"
    )


def test_two_different_questions_are_two_keys() -> None:
    """Deliberately no stemming. "nedir" and "ne kadar" ask different things,
    and a cache that collapses them answers the wrong one — a correctness bug
    dressed as a hit-rate improvement."""
    assert fingerprint("Deprem limiti nedir?", "tr") != fingerprint("Deprem limiti ne kadar?", "tr")


def test_language_is_part_of_the_key() -> None:
    """The same words in a different reply language are a different answer."""
    assert fingerprint("What is the limit?", "tr") != fingerprint("What is the limit?", "en")


def test_the_question_itself_is_not_stored() -> None:
    """A hash, so an uploaded document's questions do not outlive the
    conversation they came from in a table keyed by document."""
    digest = fingerprint("Kedimin verdiği zarar karşılanıyor mu?", "tr")
    assert "kedim" not in digest
    assert len(digest) == 64


# --- what is worth remembering ------------------------------------------------


def test_a_grounded_answer_is_cached() -> None:
    assert is_cacheable(_payload()) is True


def test_a_suppressed_answer_is_not_cached() -> None:
    """The output of a check that failed. The model is not deterministic and the
    next attempt may well be groundable; caching this would make one bad sample
    permanent and freeze the demo's most interesting behaviour into a fixture."""
    assert is_cacheable(_payload(suppressed=True)) is False


def test_a_refusal_is_not_cached() -> None:
    assert is_cacheable(_payload(refused=True, citations=[])) is False


def test_an_answer_with_no_citations_is_not_cached() -> None:
    """Either a refusal or a provider error wearing an answer's shape."""
    assert is_cacheable(_payload(citations=[])) is False


# --- reads --------------------------------------------------------------------


async def test_a_hit_reports_how_many_times_it_had_been_served_before() -> None:
    """`serve_count` comes back post-increment. Off by one here is a wrong
    number on a user's screen, not an internal detail."""
    pool = FakePool(fetchrow=[{"payload": _payload(), "serve_count": 5}])
    cache = AnswerCache(cast(Any, pool))

    hit = await cache.get(
        document_id=_ANY_ID,
        question="Deprem limiti nedir?",
        language="tr",
        prompt_version="answer_v2",
        model="claude-haiku-4-5",
    )

    assert hit is not None
    assert hit.served_before == 4


async def test_a_miss_is_none() -> None:
    cache = AnswerCache(cast(Any, FakePool(fetchrow=[None])))

    assert (
        await cache.get(
            document_id=_ANY_ID,
            question="…",
            language="tr",
            prompt_version="answer_v2",
            model="m",
        )
        is None
    )


async def test_a_failing_cache_does_not_fail_the_request() -> None:
    """An optimisation that can break answering has stopped being one."""

    class _Broken:
        async def fetchrow(self, *_: object) -> object:
            raise RuntimeError('relation "answer_cache" does not exist')

    cache = AnswerCache(cast(Any, _Broken()))

    assert (
        await cache.get(
            document_id=_ANY_ID,
            question="…",
            language="tr",
            prompt_version="answer_v2",
            model="m",
        )
        is None
    )


async def test_disabled_never_touches_the_database() -> None:
    pool = FakePool(fetchrow=[{"payload": _payload(), "serve_count": 1}])
    cache = AnswerCache(cast(Any, pool), enabled=False)

    hit = await cache.get(
        document_id=_ANY_ID,
        question="…",
        language="tr",
        prompt_version="answer_v2",
        model="m",
    )

    assert hit is None
    assert pool.queries == []


# --- the guards, asserted on the SQL ------------------------------------------
#
# These conditions live in the statement and cannot be observed through a fake
# that understands no SQL. Asserting on the text is the same trade the retention
# tests make for `not is_sample`, and for the same reason: dropping one of them
# is silent and expensive.


async def test_only_samples_are_readable_from_the_cache() -> None:
    pool = FakePool(fetchrow=[None])
    cache = AnswerCache(cast(Any, pool))

    await cache.get(
        document_id=_ANY_ID,
        question="…",
        language="tr",
        prompt_version="answer_v2",
        model="m",
    )

    assert "d.is_sample" in pool.queries[0]


async def test_only_samples_are_written_to_the_cache() -> None:
    """Entries are shared between users, so a document that is not itself
    shared must never produce one. A positive check, not an unguessable key."""
    pool = FakePool()
    cache = AnswerCache(cast(Any, pool))

    await cache.put(
        document_id=_ANY_ID,
        question="…",
        language="tr",
        prompt_version="answer_v2",
        model="m",
        payload=_payload(),
    )

    assert "d.is_sample" in pool.queries[0]


async def test_entries_age_out() -> None:
    pool = FakePool(fetchrow=[None])
    cache = AnswerCache(cast(Any, pool))

    await cache.get(
        document_id=_ANY_ID,
        question="…",
        language="tr",
        prompt_version="answer_v2",
        model="m",
    )

    assert "created_at > now()" in pool.queries[0]
    assert str(MAX_AGE_HOURS) in [str(arg) for arg in pool.log[0][1]]


@pytest.mark.parametrize("column", ["prompt_version", "model"])
async def test_the_prompt_and_the_model_are_part_of_the_lookup(column: str) -> None:
    """A prompt change must miss every entry rather than serve answers a retired
    prompt produced."""
    pool = FakePool(fetchrow=[None])
    cache = AnswerCache(cast(Any, pool))

    await cache.get(
        document_id=_ANY_ID,
        question="…",
        language="tr",
        prompt_version="answer_v2",
        model="m",
    )

    assert f"c.{column} = " in pool.queries[0]
