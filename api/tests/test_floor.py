"""The retrieval floor.

The numbers asserted here are the ones the floor was derived from, measured
against the real corpus by `eval/measure_floor.py` and recorded in
`api/retrieval/floor.py`.

An earlier version of this file opened by claiming that "if the embedding model
or its dimensionality changes, these fail". It did not. The model changed,
1536 dimensions became 1024, the whole distance distribution moved about 0.19
further out, and every test here stayed green — because they compare three
constants against a fourth constant, and none of the four knows which model is
configured. A test that asserts its own arithmetic cannot notice the world
moving underneath it.

The floor spent that period refusing 32 of the 49 answerable questions in the
golden set. `test_the_threshold_and_the_model_are_declared_together` is the
replacement guard: it fails when the configured embedding model is not the one
the number was measured in, which is the only fact that can actually detect this.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from api.config import Settings
from api.deps import build_embedder
from api.retrieval.floor import FLOOR_DISTANCE, FLOOR_MODEL, check_model, evaluate
from api.retrieval.types import RetrievedChunk

# From the measurement in floor.py's docstring, in the space of voyage-4-lite.
FURTHEST_ANSWERABLE = 0.6967
NEAREST_UNRELATED = 0.7339

# The lexical probes, which used to sit comfortably inside the floor and no
# longer do. `1.800.000` is the nearest of the three that fall outside it.
FURTHEST_LEXICAL = 0.8010
NEAREST_LEXICAL_BEYOND_THE_FLOOR = 0.7266


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


def test_the_question_that_was_refused_in_production_is_answered() -> None:
    """`Teminatlar nelerdir?` against a policy whose first page is a coverage
    schedule, measured at 0.5449 while the floor stood at 0.46."""
    assert evaluate([chunk(distance=0.5449)]).below is False


# --- the guard the old tests only claimed to be --------------------------------


def test_the_shipped_default_model_is_the_one_the_floor_was_measured_in() -> None:
    """The one assertion that can detect the failure above.

    It builds the embedder the way the application does rather than reading
    `Settings.voyage_model` directly, so changing which provider wins also
    fails here — that substitution is what happened, and reading the field
    would have missed it.

    A deployment can still override `VOYAGE_MODEL` in its environment, which no
    unit test can see; `main.py` checks that at startup and refuses to boot.
    """
    embedder = build_embedder(
        Settings(app_env="development", voyage_api_key="pa-test", _env_file=None)
    )

    assert check_model(embedder.model) is None, (
        f"Embeddings default to {embedder.model} but FLOOR_DISTANCE was measured "
        f"against {FLOOR_MODEL}. Re-run `python -m eval.measure_floor`."
    )


def test_the_gemini_fallback_is_not_compatible_with_the_floor() -> None:
    """Falling back to Gemini silently reinstates the mismatch: the floor's
    number means nothing in that space. It is a warning in development and a
    refusal to boot when deployed, not something to discover from a user."""
    embedder = build_embedder(
        Settings(app_env="development", voyage_api_key=None, google_api_key="x", _env_file=None)
    )

    assert check_model(embedder.model) is not None


def test_a_different_model_is_a_complaint_that_names_both() -> None:
    complaint = check_model("some-other-embedding-model")

    assert complaint is not None
    assert FLOOR_MODEL in complaint
    assert "some-other-embedding-model" in complaint
    assert "measure_floor" in complaint


@pytest.mark.parametrize("model", ["voyage-4", "voyage-4-lite-2", "VOYAGE-4-LITE"])
def test_a_near_miss_is_still_a_mismatch(model: str) -> None:
    """Same vendor, same family, similar name, different space. Treating any of
    these as close enough is precisely how 0.46 survived the move to Voyage."""
    assert check_model(model) is not None


# --- the decision -------------------------------------------------------------


def test_keyword_matches_do_not_rescue_an_off_topic_question() -> None:
    """The veto that was measured and removed, pinned so it does not return.

    "What is the capital of Australia?" matched 8 of 8 chunks in the commercial
    policy — the tsquery is rewritten to OR, so one shared token is enough.
    Letting that block a refusal cost 6 of 18 unrelated queries.
    """
    verdict = evaluate([chunk(distance=0.81, keyword_rank=1)])
    assert verdict.below is True
    assert verdict.keyword_hits == 1  # recorded, and reported, but not acted on


def test_an_identifier_only_query_can_be_refused_and_that_is_documented() -> None:
    """A known limitation rather than a passing test dressed as a feature.

    In the Gemini space every lexical probe landed inside the floor, which is
    what retired the keyword veto. In this one, `1.800.000` and `%20` land
    outside it. Reinstating the veto does not help — they matched 1 chunk each
    while "Ignore previous instructions" matched 7. Asserted so that a future
    change which fixes it fails here and gets the docstring corrected.
    """
    assert evaluate([chunk(distance=NEAREST_LEXICAL_BEYOND_THE_FLOOR)]).below is True
    assert evaluate([chunk(distance=FURTHEST_LEXICAL, keyword_rank=1)]).below is True


def test_the_nearest_chunk_decides_not_the_average() -> None:
    """One good passage is enough to answer from; the rest are noise."""
    candidates = [chunk(distance=0.48), chunk(distance=0.83), chunk(distance=0.91)]
    assert evaluate(candidates).below is False


def test_a_query_with_no_vector_neighbours_at_all_is_below_the_floor() -> None:
    """Keyword-only candidates carry no distance. Nothing to measure is not the
    same as measuring nothing, and the safe reading is 'as far as possible'."""
    assert evaluate([chunk(distance=None, keyword_rank=3)]).below is True


def test_an_empty_retrieval_is_below_the_floor() -> None:
    assert evaluate([]).below is True


def test_the_verdict_explains_itself() -> None:
    """A refusal that never reached a model still has to be inspectable."""
    verdict = evaluate([chunk(distance=0.7412), chunk(distance=0.79, keyword_rank=2)])
    assert verdict.as_dict == {
        "below": True,
        "best_distance": 0.7412,
        "keyword_hits": 1,
        "candidates": 2,
    }
