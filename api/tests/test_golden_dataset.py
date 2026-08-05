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

from pathlib import Path

from eval.dataset import load, stats, validate

QUESTIONS = load()

# The adversarial set. Separate numbers, same drift protection: a question whose
# planted fact has been edited out of its document measures nothing, and does it
# silently.
HARD = load(Path(__file__).resolve().parents[2] / "eval" / "golden" / "questions_hard.json")


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


# -----------------------------------------------------------------------------
# the hard set
# -----------------------------------------------------------------------------


def test_the_hard_set_is_coherent_too() -> None:
    problems = validate(HARD)
    assert not problems, "hard dataset problems:\n  " + "\n  ".join(problems)


def test_the_hard_set_exercises_both_adversarial_documents() -> None:
    """One document contradicts itself, the other is set in two columns. A set
    that only covered one of them would be measuring one failure mode and
    reporting two."""
    documents = {q.document for q in HARD}
    assert documents == {"celiskili-seyahat-tr", "iki-sutun-kasko-tr"}


def test_the_contradictions_name_both_sides() -> None:
    """The whole point of a contradiction question.

    `expected_evidence` listing only the clause that grants cover would score an
    answer citing only that clause as a success — which is exactly the failure
    being looked for.
    """
    for question in (q for q in HARD if q.category == "contradiction"):
        assert len(question.expected_evidence) >= 2, question.id


def test_the_hard_set_keeps_a_control_for_each_trap() -> None:
    """A set made only of traps cannot distinguish a system that is careful from
    one that has simply stopped answering."""
    assert any(q.category == "negative" for q in HARD)
    assert any(q.category == "factual" for q in HARD)
