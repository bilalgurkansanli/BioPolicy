"""Scoring for the evaluation harness.

Pure functions over recorded results, so the arithmetic behind every published
number is testable without spending anything.

## Definitions, and why they are these definitions

**Retrieval hit — all evidence, not any.** A question like "what is the
earthquake limit?" lists both `Deprem ve Yanardağ Püskürmesi` and `1.800.000` as
evidence. Retrieving a chunk with the peril but not the figure has not retrieved
the answer; it has retrieved the question restated. Scoring `any` would let a
system that never returns coverage tables look competent.

**Refusal accuracy and false-refusal rate are reported together, always.** They
trade against each other, and either alone is trivially gamed: a system that
refuses everything scores 100% refusal accuracy, and one that never refuses
scores a 0% false-refusal rate. Neither is a working product. Any report that
shows one without the other is hiding something.

**Groundedness averages over answers that were actually served.** Including
suppressed answers would mix "we checked and it was well-supported" with "we
checked, it wasn't, and we withheld it" — the second is a success of the system
and would drag down a number meant to describe what users see. Suppressions are
counted separately, as caught hallucinations, which is the more honest place for
them.

**Cost and latency are p50 and p95, never the mean.** One 40-second cold start
moves a mean and tells you nothing about the typical experience. p95 is where
users decide the product is broken.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from eval.dataset import GoldenQuestion


@dataclass(slots=True)
class QuestionResult:
    """What happened when one golden question was run."""

    question: GoldenQuestion

    # --- what the system decided -------------------------------------------
    answer_found: bool
    """True when an answer was served. False for any refusal, including suppression."""

    suppressed: bool = False
    suppression_reason: str | None = None

    # --- retrieval ----------------------------------------------------------
    evidence_found: tuple[str, ...] = ()
    """Expected evidence spans located anywhere in the retrieved chunks."""

    first_hit_rank: int | None = None
    """1-based rank of the highest-ranked chunk containing any expected evidence."""

    retrieved_count: int = 0

    # --- citations ----------------------------------------------------------
    citations_offered: int = 0
    citations_kept: int = 0

    # --- verification -------------------------------------------------------
    groundedness: float | None = None

    # --- cost -------------------------------------------------------------
    latency_ms: float = 0.0
    cost_usd: float = 0.0

    error: str | None = None

    @property
    def retrieval_hit(self) -> bool:
        """Every expected span was retrieved. Negatives have nothing to retrieve."""
        expected = set(self.question.expected_evidence)
        if not expected:
            return True
        return expected <= set(self.evidence_found)

    @property
    def decision_correct(self) -> bool:
        return self.answer_found == self.question.expected_answer_found


@dataclass(slots=True)
class RetrievalMetrics:
    recall_at_k: float
    mrr: float
    answerable_count: int


@dataclass(slots=True)
class RefusalMetrics:
    """Both directions, always reported together."""

    refusal_accuracy: float
    """Of the questions the document genuinely cannot answer, how many were refused."""

    false_refusal_rate: float
    """Of the answerable questions, how many were refused anyway."""

    negatives: int
    answerables: int
    correct_refusals: int
    false_refusals: int

    @property
    def balanced_accuracy(self) -> float:
        """Mean of the two directions.

        Present specifically because it cannot be gamed by refusing everything
        or by never refusing — both strategies score 0.5.
        """
        return (self.refusal_accuracy + (1.0 - self.false_refusal_rate)) / 2


@dataclass(slots=True)
class CitationMetrics:
    validity: float
    """Fraction of offered citations that survived binding."""

    offered: int
    kept: int
    suppressions: int
    """Answers withheld because every citation failed. Caught hallucinations."""


@dataclass(slots=True)
class CostMetrics:
    total_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    mean_cost_per_query_usd: float


@dataclass(slots=True)
class Report:
    retrieval: RetrievalMetrics
    refusal: RefusalMetrics
    citations: CitationMetrics
    groundedness_mean: float | None
    groundedness_distribution: dict[str, int]
    cost: CostMetrics
    by_category: dict[str, RetrievalMetrics] = field(default_factory=dict)
    category_decision_accuracy: dict[str, float] = field(default_factory=dict)
    groundedness_by_category: dict[str, float] = field(default_factory=dict)
    """Mean groundedness per category, over served answers.

    Broken out because the aggregate hides the finding that matters: the
    verifier does not score every kind of answer alike, and the category it
    scores lowest may be the one the product exists to handle.
    """

    errors: int = 0
    total: int = 0


def retrieval_metrics(results: list[QuestionResult]) -> RetrievalMetrics:
    """Recall@k and MRR over the answerable questions only.

    Negatives are excluded: there is no correct chunk to find, so including them
    would inflate recall with questions that cannot be got wrong.
    """
    answerable = [r for r in results if r.question.expected_answer_found]
    if not answerable:
        return RetrievalMetrics(recall_at_k=0.0, mrr=0.0, answerable_count=0)

    hits = sum(1 for r in answerable if r.retrieval_hit)
    reciprocal = sum(1.0 / r.first_hit_rank for r in answerable if r.first_hit_rank)

    return RetrievalMetrics(
        recall_at_k=hits / len(answerable),
        mrr=reciprocal / len(answerable),
        answerable_count=len(answerable),
    )


def refusal_metrics(results: list[QuestionResult]) -> RefusalMetrics:
    negatives = [r for r in results if not r.question.expected_answer_found]
    answerables = [r for r in results if r.question.expected_answer_found]

    correct_refusals = sum(1 for r in negatives if not r.answer_found)
    false_refusals = sum(1 for r in answerables if not r.answer_found)

    return RefusalMetrics(
        refusal_accuracy=correct_refusals / len(negatives) if negatives else 0.0,
        false_refusal_rate=false_refusals / len(answerables) if answerables else 0.0,
        negatives=len(negatives),
        answerables=len(answerables),
        correct_refusals=correct_refusals,
        false_refusals=false_refusals,
    )


def citation_metrics(results: list[QuestionResult]) -> CitationMetrics:
    offered = sum(r.citations_offered for r in results)
    kept = sum(r.citations_kept for r in results)
    return CitationMetrics(
        validity=kept / offered if offered else 0.0,
        offered=offered,
        kept=kept,
        suppressions=sum(1 for r in results if r.suppressed),
    )


def groundedness_summary(results: list[QuestionResult]) -> tuple[float | None, dict[str, int]]:
    """Mean and banded distribution over answers that were actually served."""
    scores = [r.groundedness for r in results if r.groundedness is not None and r.answer_found]
    distribution = {"high (>=0.8)": 0, "medium (0.5-0.8)": 0, "low (<0.5)": 0}
    for score in scores:
        if score >= 0.8:
            distribution["high (>=0.8)"] += 1
        elif score >= 0.5:
            distribution["medium (0.5-0.8)"] += 1
        else:
            distribution["low (<0.5)"] += 1

    return (statistics.fmean(scores) if scores else None), distribution


def cost_metrics(results: list[QuestionResult]) -> CostMetrics:
    latencies = sorted(r.latency_ms for r in results)
    total = sum(r.cost_usd for r in results)

    return CostMetrics(
        total_usd=total,
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        mean_cost_per_query_usd=total / len(results) if results else 0.0,
    )


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile. Exact and obvious, which matters more here than
    interpolation subtleties on a 59-sample set."""
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, round(fraction * len(sorted_values)) - 1))
    return sorted_values[index]


def build_report(results: list[QuestionResult]) -> Report:
    by_category: dict[str, RetrievalMetrics] = {}
    decision_accuracy: dict[str, float] = {}

    grounded_by_category: dict[str, float] = {}

    categories = sorted({r.question.category for r in results})
    for category in categories:
        subset = [r for r in results if r.question.category == category]
        by_category[category] = retrieval_metrics(subset)
        decision_accuracy[category] = sum(1 for r in subset if r.decision_correct) / len(subset)
        scores = [r.groundedness for r in subset if r.groundedness is not None and r.answer_found]
        if scores:
            grounded_by_category[category] = statistics.fmean(scores)

    mean, distribution = groundedness_summary(results)

    return Report(
        retrieval=retrieval_metrics(results),
        refusal=refusal_metrics(results),
        citations=citation_metrics(results),
        groundedness_mean=mean,
        groundedness_distribution=distribution,
        cost=cost_metrics(results),
        by_category=by_category,
        category_decision_accuracy=decision_accuracy,
        groundedness_by_category=grounded_by_category,
        errors=sum(1 for r in results if r.error),
        total=len(results),
    )


def locate_evidence(
    question: GoldenQuestion, retrieved_texts: list[str]
) -> tuple[tuple[str, ...], int | None]:
    """Which expected spans were retrieved, and at what rank the first one appeared.

    Matching is a plain substring test on the chunk text. Deliberately strict:
    the evidence spans are copied verbatim from the source documents, so a miss
    means the text genuinely was not retrieved, not that the comparison was
    fussy.
    """
    found: list[str] = []
    first_rank: int | None = None

    for span in question.expected_evidence:
        for rank, text in enumerate(retrieved_texts, start=1):
            if span in text:
                found.append(span)
                if first_rank is None or rank < first_rank:
                    first_rank = rank
                break

    return tuple(found), first_rank
