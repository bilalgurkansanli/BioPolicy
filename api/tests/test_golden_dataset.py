"""The golden dataset must stay coherent with the documents it describes.

An eval harness is only as trustworthy as its dataset, and a dataset drifts
silently: someone rewords a clause in `sample_content.py`, a planted fact moves,
and from then on the harness measures a question whose expected answer no longer
exists — scoring it as a retrieval failure and quietly depressing every metric
that depends on it.

These tests run in normal CI, not under the `eval` marker, because they cost
nothing and they are what stops the published numbers from being nonsense.
"""

from __future__ import annotations

from eval.dataset import load, stats, validate

QUESTIONS = load()


def test_the_dataset_is_internally_coherent() -> None:
    problems = validate(QUESTIONS)
    assert not problems, "golden dataset problems:\n  " + "\n  ".join(problems)


def test_every_planted_fact_still_exists_in_its_document() -> None:
    """Covered by validate(), asserted separately because it is the point.

    This is the check that catches an edit to sample_content.py silently
    invalidating a question.
    """
    missing = [p for p in validate(QUESTIONS) if "does not appear" in p]
    assert not missing, "\n".join(missing)


def test_the_dataset_is_large_enough_to_mean_anything() -> None:
    assert len(QUESTIONS) >= 40


def test_roughly_a_third_are_adversarial_negatives() -> None:
    """The most important category, and the easiest one to under-supply.

    A system that never refuses scores well on the other three and is worthless.
    Without a substantial negative set, refusal accuracy is measured on too few
    samples to distinguish a careful system from a lucky one.
    """
    share = stats(QUESTIONS).negative_share
    assert 0.25 <= share <= 0.40, f"negatives are {share:.0%} of the set"


def test_every_category_is_represented() -> None:
    by_category = stats(QUESTIONS).by_category
    for category in ("factual", "table", "multi_clause", "negative", "cross_lingual"):
        assert by_category.get(category, 0) >= 3, f"{category} has too few questions"


def test_both_languages_are_represented() -> None:
    by_language = stats(QUESTIONS).by_language
    assert by_language.get("tr", 0) >= 10
    assert by_language.get("en", 0) >= 10


def test_every_document_is_exercised() -> None:
    by_document = stats(QUESTIONS).by_document
    assert len(by_document) == 3
    assert all(count >= 8 for count in by_document.values())


def test_cross_lingual_questions_really_cross_a_language() -> None:
    """A cross-lingual question asked in the document's own language tests nothing."""
    from eval.sample_content import ALL_DOCUMENTS

    doc_lang = {d["slug"]: d["lang"] for d in ALL_DOCUMENTS}
    for question in QUESTIONS:
        if question.category == "cross_lingual":
            assert question.lang != doc_lang[question.document], (
                f"{question.id} is marked cross_lingual but is asked in the document's "
                f"own language ({question.lang})"
            )


def test_negatives_are_spread_across_all_three_documents() -> None:
    """Negatives concentrated in one document would measure that document only."""
    documents = {q.document for q in QUESTIONS if q.is_negative}
    assert len(documents) == 3
