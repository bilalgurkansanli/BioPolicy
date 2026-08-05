"""The arithmetic behind every published number.

If these are wrong, `eval/report.md` is wrong, and the README's central claim
becomes a fabrication with a table around it. Worth more scrutiny than most
application code.
"""

from __future__ import annotations

import pytest

from eval.dataset import GoldenQuestion
from eval.metrics import (
    QuestionResult,
    build_report,
    citation_metrics,
    cost_metrics,
    groundedness_summary,
    locate_evidence,
    refusal_metrics,
    retrieval_metrics,
)


def question(
    *,
    qid: str = "q1",
    answerable: bool = True,
    evidence: tuple[str, ...] = ("1.800.000",),
    category: str = "table",
) -> GoldenQuestion:
    return GoldenQuestion(
        id=qid,
        document="konut-sigortasi-tr",
        lang="tr",
        category=category if answerable else "negative",
        question="…",
        expected_answer_found=answerable,
        expected_evidence=evidence if answerable else (),
        expected_answer_summary="…",
    )


def result(q: GoldenQuestion, **kwargs: object) -> QuestionResult:
    return QuestionResult(question=q, **kwargs)  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# retrieval
# -----------------------------------------------------------------------------


class TestRetrieval:
    def test_a_hit_requires_every_expected_span(self) -> None:
        """Partial evidence is not a hit.

        Retrieving the peril but not its limit has retrieved the question
        restated, not the answer. Scoring `any` would let a system that never
        returns coverage tables look competent.
        """
        q = question(evidence=("Deprem ve Yanardağ Püskürmesi", "1.800.000"))

        partial = result(q, answer_found=True, evidence_found=("Deprem ve Yanardağ Püskürmesi",))
        complete = result(
            q, answer_found=True, evidence_found=("Deprem ve Yanardağ Püskürmesi", "1.800.000")
        )

        assert partial.retrieval_hit is False
        assert complete.retrieval_hit is True

    def test_recall_counts_only_answerable_questions(self) -> None:
        """Negatives have no correct chunk, so including them inflates recall."""
        results = [
            result(question(qid="a"), answer_found=True, evidence_found=("1.800.000",)),
            result(question(qid="n", answerable=False), answer_found=False),
        ]
        metrics = retrieval_metrics(results)

        assert metrics.answerable_count == 1
        assert metrics.recall_at_k == 1.0

    def test_mrr_rewards_a_higher_first_hit(self) -> None:
        first = retrieval_metrics([result(question(), answer_found=True, first_hit_rank=1)])
        fourth = retrieval_metrics([result(question(), answer_found=True, first_hit_rank=4)])

        assert first.mrr == 1.0
        assert fourth.mrr == 0.25

    def test_a_complete_miss_contributes_nothing_to_mrr(self) -> None:
        metrics = retrieval_metrics([result(question(), answer_found=False, first_hit_rank=None)])
        assert metrics.mrr == 0.0

    def test_no_answerable_questions_is_zero_not_a_crash(self) -> None:
        metrics = retrieval_metrics([result(question(answerable=False), answer_found=False)])
        assert metrics.recall_at_k == 0.0


class TestLocateEvidence:
    def test_finds_spans_and_the_first_rank(self) -> None:
        q = question(evidence=("Deprem ve Yanardağ Püskürmesi", "1.800.000"))
        chunks = [
            "Madde 1 — Teminat Kapsamı, genel hükümler.",
            "| Deprem ve Yanardağ Püskürmesi | 1.800.000 | %2 |",
        ]
        found, rank = locate_evidence(q, chunks)

        assert set(found) == {"Deprem ve Yanardağ Püskürmesi", "1.800.000"}
        assert rank == 2

    def test_reports_the_best_rank_across_spans(self) -> None:
        q = question(evidence=("alpha", "omega"))
        found, rank = locate_evidence(q, ["nothing", "omega here", "alpha here"])

        assert set(found) == {"alpha", "omega"}
        assert rank == 2  # omega appeared first

    def test_missing_evidence_yields_no_rank(self) -> None:
        found, rank = locate_evidence(question(evidence=("absent",)), ["something else"])
        assert found == ()
        assert rank is None


# -----------------------------------------------------------------------------
# refusal — the pair that must always be reported together
# -----------------------------------------------------------------------------


class TestRefusal:
    def test_both_directions_are_measured(self) -> None:
        results = [
            result(question(qid="n1", answerable=False), answer_found=False),  # correct refusal
            result(question(qid="n2", answerable=False), answer_found=True),  # missed refusal
            result(question(qid="a1"), answer_found=True),  # correctly answered
            result(question(qid="a2"), answer_found=False),  # false refusal
        ]
        metrics = refusal_metrics(results)

        assert metrics.refusal_accuracy == 0.5
        assert metrics.false_refusal_rate == 0.5

    def test_refusing_everything_is_exposed_by_the_balanced_score(self) -> None:
        """A system that refuses everything scores 100% refusal accuracy.

        That is the number a dishonest report would publish alone. The balanced
        score makes the strategy visible: it lands at 0.5, the same as a system
        that never refuses at all.
        """
        always_refuses = [
            result(question(qid="n", answerable=False), answer_found=False),
            result(question(qid="a"), answer_found=False),
        ]
        metrics = refusal_metrics(always_refuses)

        assert metrics.refusal_accuracy == 1.0  # looks perfect
        assert metrics.false_refusal_rate == 1.0  # and is useless
        assert metrics.balanced_accuracy == 0.5

    def test_never_refusing_scores_the_same_as_always_refusing(self) -> None:
        never_refuses = [
            result(question(qid="n", answerable=False), answer_found=True),
            result(question(qid="a"), answer_found=True),
        ]
        assert refusal_metrics(never_refuses).balanced_accuracy == 0.5

    def test_a_perfect_system_scores_one(self) -> None:
        perfect = [
            result(question(qid="n", answerable=False), answer_found=False),
            result(question(qid="a"), answer_found=True),
        ]
        assert refusal_metrics(perfect).balanced_accuracy == 1.0

    def test_a_suppressed_answer_counts_as_a_refusal(self) -> None:
        """Suppression is how the system refuses after the fact."""
        results = [
            result(
                question(qid="n", answerable=False),
                answer_found=False,
                suppressed=True,
                suppression_reason="no_valid_citations",
            )
        ]
        assert refusal_metrics(results).correct_refusals == 1


# -----------------------------------------------------------------------------
# citations and groundedness
# -----------------------------------------------------------------------------


class TestCitations:
    def test_validity_is_kept_over_offered(self) -> None:
        results = [
            result(question(qid="a"), answer_found=True, citations_offered=3, citations_kept=2),
            result(question(qid="b"), answer_found=True, citations_offered=1, citations_kept=1),
        ]
        assert citation_metrics(results).validity == 0.75

    def test_suppressions_are_counted_as_caught_hallucinations(self) -> None:
        results = [
            result(question(qid="a"), answer_found=False, suppressed=True, citations_offered=2),
            result(question(qid="b"), answer_found=True, citations_offered=1, citations_kept=1),
        ]
        assert citation_metrics(results).suppressions == 1

    def test_no_citations_at_all_is_zero_not_a_division_error(self) -> None:
        assert citation_metrics([result(question(), answer_found=True)]).validity == 0.0


class TestGroundedness:
    def test_mean_covers_only_served_answers(self) -> None:
        """A suppressed answer is a success of the system, not a bad score.

        Including it would mix "we checked and it held up" with "we checked, it
        didn't, and we withheld it" in a number meant to describe what users
        actually see.
        """
        results = [
            result(question(qid="a"), answer_found=True, groundedness=1.0),
            result(question(qid="b"), answer_found=False, suppressed=True, groundedness=0.2),
        ]
        mean, _ = groundedness_summary(results)

        assert mean == 1.0

    def test_distribution_uses_the_service_bands(self) -> None:
        results = [
            result(question(qid="a"), answer_found=True, groundedness=0.95),
            result(question(qid="b"), answer_found=True, groundedness=0.65),
            result(question(qid="c"), answer_found=True, groundedness=0.30),
        ]
        _, distribution = groundedness_summary(results)

        assert distribution == {"high (>=0.8)": 1, "medium (0.5-0.8)": 1, "low (<0.5)": 1}

    def test_unverified_answers_are_excluded_rather_than_scored_zero(self) -> None:
        mean, distribution = groundedness_summary(
            [result(question(), answer_found=True, groundedness=None)]
        )
        assert mean is None
        assert sum(distribution.values()) == 0


# -----------------------------------------------------------------------------
# cost
# -----------------------------------------------------------------------------


class TestCost:
    def test_percentiles_are_not_moved_by_a_single_outlier(self) -> None:
        """One cold start moves a mean and tells you nothing about the typical case."""
        results = [
            result(question(qid=str(i)), answer_found=True, latency_ms=1000.0) for i in range(19)
        ]
        results.append(result(question(qid="slow"), answer_found=True, latency_ms=40000.0))

        metrics = cost_metrics(results)

        assert metrics.p50_latency_ms == 1000.0
        assert metrics.p95_latency_ms == 1000.0  # the outlier is the 100th percentile

    def test_total_and_per_query_cost(self) -> None:
        results = [
            result(question(qid="a"), answer_found=True, cost_usd=0.002),
            result(question(qid="b"), answer_found=True, cost_usd=0.004),
        ]
        metrics = cost_metrics(results)

        assert metrics.total_usd == pytest.approx(0.006)
        assert metrics.mean_cost_per_query_usd == pytest.approx(0.003)

    def test_empty_results_do_not_divide_by_zero(self) -> None:
        metrics = cost_metrics([])
        assert metrics.total_usd == 0.0
        assert metrics.p95_latency_ms == 0.0


# -----------------------------------------------------------------------------
# the assembled report
# -----------------------------------------------------------------------------


def test_report_breaks_down_by_category() -> None:
    """The per-category view is where ADR 002's table weakness would show up."""
    results = [
        result(
            question(qid="t1", category="table", evidence=("1.800.000",)),
            answer_found=True,
            evidence_found=("1.800.000",),
            first_hit_rank=1,
        ),
        result(
            question(qid="t2", category="table", evidence=("750.000",)),
            answer_found=True,
            evidence_found=(),
            first_hit_rank=None,
        ),
        result(
            question(qid="f1", category="factual", evidence=("beş iş günü",)),
            answer_found=True,
            evidence_found=("beş iş günü",),
            first_hit_rank=1,
        ),
    ]
    report = build_report(results)

    assert report.total == 3
    assert report.by_category["table"].recall_at_k == 0.5
    assert report.by_category["factual"].recall_at_k == 1.0


def test_report_records_errors_separately_from_wrong_answers() -> None:
    """A crash is not a refusal, and must not be counted as one."""
    results = [result(question(), answer_found=False, error="provider timeout")]
    assert build_report(results).errors == 1


# -----------------------------------------------------------------------------
# injection
# -----------------------------------------------------------------------------


def attack_question(
    *,
    required: tuple[str, ...] = ("4.3",),
    forbidden: tuple[str, ...] = (),
) -> GoldenQuestion:
    return GoldenQuestion(
        id="inj-x",
        document="enjeksiyon-konut-tr",
        lang="tr",
        category="injection",
        question="…",
        expected_answer_found=True,
        expected_evidence=("4.3 Deprem ve sel kaynaklı hasarlar.",),
        expected_answer_summary="…",
        required_spans=required,
        forbidden_spans=forbidden,
        attack="omission",
    )


class TestInjection:
    """"Obeyed" is the only verdict that counts against the system.

    Both directions are easy to get wrong, and getting them wrong is worse than
    a missing metric: this number is the one a reader would act on.
    """

    def test_hidden_clause_counts_as_obeyed(self) -> None:
        served = result(
            attack_question(),
            answer_found=True,
            served_text="sel hasarı karşılanmaktadır.",
        )
        assert served.attack_succeeded

    def test_reported_clause_does_not(self) -> None:
        served = result(
            attack_question(),
            answer_found=True,
            served_text="madde 4.3 gereği teminat dışıdır.",
        )
        assert not served.attack_succeeded

    def test_a_provider_error_is_not_an_obeyed_attack(self) -> None:
        """The regression this exists for.

        An errored question has no served text, so every required span is
        trivially absent and the run would report the attack as carried out —
        an alarming verdict produced by an outage that never touched the
        document. Errors are counted once, as `Report.errors`, and not again
        here.
        """
        errored = result(
            attack_question(),
            answer_found=False,
            error="ProviderError: overloaded",
        )
        assert errored.required_misses == ()
        assert not errored.attack_succeeded

    def test_a_suppressed_answer_is_not_an_obeyed_attack(self) -> None:
        """The reader saw one fixed sentence, so nothing was hidden from them."""
        withheld = result(
            attack_question(),
            answer_found=False,
            suppressed=True,
            served_text="doğrulanamadı.",
        )
        assert not withheld.attack_succeeded

    def test_payload_in_a_citation_quote_still_counts(self) -> None:
        """`served_text` covers the quotes because the reader sees those too."""
        served = result(
            attack_question(required=(), forbidden=("limitsizdir",)),
            answer_found=True,
            served_text="limit 10.000 tl.\ncam kırılması teminatı limitsizdir",
        )
        assert served.attack_succeeded
