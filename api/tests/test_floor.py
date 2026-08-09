"""The retrieval floor.

The numbers asserted here are the ones the floor was derived from, measured
against the real corpus and recorded in `api/retrieval/floor.py`. They are in a
test because the threshold is only meaningful relative to that distribution: if
the embedding model or its dimensionality changes, these fail, and failing is
the correct outcome — the constant would have to be re-derived rather than
nudged until the tests pass again.
"""

from __future__ import annotations

from uuid import uuid4

from api.retrieval.floor import FLOOR_DISTANCE, evaluate
from api.retrieval.types import RetrievedChunk

# From the measurement in floor.py's docstring.
FURTHEST_ANSWERABLE = 0.4194
NEAREST_UNRELATED = 0.4681
FURTHEST_LEXICAL = 0.4040


def chunk(*, distance: float | None = None, keyword_rank: int | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        content="Madde 4.1 — Evcil hayvanların sigortalı eşyaya verdiği zararlar.",
        content_type="text",
        page_start=1,
        page_end=1,
        section_path="Madde 4",
        vector_rank=1 if distance is not None else None,
        keyword_rank=keyword_rank,
        vector_distance=distance,
    )


# --- the boundary -------------------------------------------------------------


def test_the_furthest_answerable_question_measured_still_passes() -> None:
    """The margin that matters. A false refusal costs a user their question."""
    assert evaluate([chunk(distance=FURTHEST_ANSWERABLE)]).below is False


def test_the_nearest_unrelated_question_measured_is_refused() -> None:
    assert evaluate([chunk(distance=NEAREST_UNRELATED)]).below is True


def test_the_threshold_sits_inside_the_gap_between_them() -> None:
    """Not an implementation detail — it is the finding the floor rests on.

    If these two ever cross, no threshold separates the populations and the
    floor should be deleted rather than retuned.
    """
    assert FURTHEST_ANSWERABLE < FLOOR_DISTANCE < NEAREST_UNRELATED


def test_a_lexical_query_is_protected_by_distance_alone() -> None:
    """`POL-2026-0041` scored 0.3442 with zero keyword hits.

    This is the case the removed keyword veto was written for. Distance already
    covers it, which is why the veto is gone.
    """
    assert evaluate([chunk(distance=FURTHEST_LEXICAL, keyword_rank=None)]).below is False


# --- the decision -------------------------------------------------------------


def test_keyword_matches_do_not_rescue_an_off_topic_question() -> None:
    """The veto that was measured and removed, pinned so it does not return.

    "What is the capital of Australia?" matched 8 of 8 chunks in the commercial
    policy — the tsquery is rewritten to OR, so one shared token is enough.
    Letting that block a refusal cost 6 of 18 unrelated queries.
    """
    verdict = evaluate([chunk(distance=0.51, keyword_rank=1)])
    assert verdict.below is True
    assert verdict.keyword_hits == 1  # recorded, and reported, but not acted on


def test_the_nearest_chunk_decides_not_the_average() -> None:
    """One good passage is enough to answer from; the rest are noise."""
    candidates = [chunk(distance=0.30), chunk(distance=0.58), chunk(distance=0.61)]
    assert evaluate(candidates).below is False


def test_a_query_with_no_vector_neighbours_at_all_is_below_the_floor() -> None:
    """Keyword-only candidates carry no distance. Nothing to measure is not the
    same as measuring nothing, and the safe reading is 'as far as possible'."""
    assert evaluate([chunk(distance=None, keyword_rank=3)]).below is True


def test_an_empty_retrieval_is_below_the_floor() -> None:
    assert evaluate([]).below is True


def test_the_verdict_explains_itself() -> None:
    """A refusal that never reached a model still has to be inspectable."""
    verdict = evaluate([chunk(distance=0.4823), chunk(distance=0.52, keyword_rank=2)])
    assert verdict.as_dict == {
        "below": True,
        "best_distance": 0.4823,
        "keyword_hits": 1,
        "candidates": 2,
    }
