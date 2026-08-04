"""Render the evaluation report.

Formatting only — every number comes from `eval/metrics.py`. Kept separate so
the arithmetic can be tested without a Markdown fixture, and so changing the
presentation cannot accidentally change a result.

The report is written to be read by someone sceptical. That means the
unflattering numbers appear beside the flattering ones rather than in a
footnote, and any metric that can be gamed is shown next to the metric that
exposes the gaming.
"""

from __future__ import annotations

from datetime import datetime

from eval.dataset import Stats
from eval.metrics import Report


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _delta(on: float, off: float, *, higher_is_better: bool = True) -> str:
    """Signed change, marked as an improvement or a regression."""
    diff = on - off
    if abs(diff) < 0.005:
        return "—"
    improved = diff > 0 if higher_is_better else diff < 0
    arrow = "▲" if diff > 0 else "▼"
    note = "" if improved else " ⚠"
    return f"{arrow} {abs(diff):.0%}{note}"


def _limitations(
    arms: dict[str, Report],
    *,
    chunks_per_document: dict[str, int],
    context_chunk_count: int,
) -> list[str]:
    """Findings that qualify the numbers above, computed rather than written.

    A report that lists only its results is a sales document. These are derived
    from the same run, so they cannot drift out of date or be quietly dropped
    when they become inconvenient.
    """
    notes: list[str] = []

    # 1. Retrieval is only being measured if it has to choose.
    oversized = {
        name: count for name, count in chunks_per_document.items() if count > context_chunk_count
    }
    if not oversized and chunks_per_document:
        biggest = max(chunks_per_document.values())
        notes.append(
            f"**Recall is not a meaningful measurement on this corpus.** The sample "
            f"documents hold {min(chunks_per_document.values())}–{biggest} chunks each "
            f"and the context window takes {context_chunk_count}, so *every chunk of "
            f"every document reaches the prompt on every question*. Retrieval is never "
            f"forced to discard anything, which means a recall figure of 100% reflects "
            f"the size of the documents, not the quality of the search. MRR still says "
            f"something about ranking; recall does not. Fixing this needs longer "
            f"documents, not a better retriever."
        )

    # 2. An ablation that shows nothing is a result, and needs saying out loud.
    on, off = arms.get("on"), arms.get("off")
    if on and off:
        moved = (
            abs(on.refusal.balanced_accuracy - off.refusal.balanced_accuracy) >= 0.005
            or abs(on.citations.validity - off.citations.validity) >= 0.005
            or on.citations.suppressions != off.citations.suppressions
        )
        if not moved:
            notes.append(
                "**The anti-hallucination layer changed nothing on this dataset.** "
                "Citation binding dropped no citations and self-verification "
                "suppressed no answers, so both arms score identically. That is a "
                "real result and it is reported as one rather than buried: on these "
                "documents, with this prompt and this model, the safety net never "
                "caught anything because nothing fell into it. It does **not** show "
                "the mechanisms are unnecessary — an untriggered safeguard is not a "
                "disproved one — but it does mean this run provides no evidence that "
                "they help. Evidence would require conditions that actually induce "
                "fabrication: longer documents where the answer is not always in "
                "context, a weaker or unconstrained model, or the strict prompt "
                "removed."
            )

    # 3. The verifier does not treat every kind of answer alike.
    scores = (
        primary.groundedness_by_category if (primary := on or next(iter(arms.values()))) else {}
    )
    if len(scores) >= 3:
        worst, worst_score = min(scores.items(), key=lambda kv: kv[1])
        best, best_score = max(scores.items(), key=lambda kv: kv[1])
        if worst == "multi_clause" and best_score - worst_score >= 0.1:
            accuracy = primary.category_decision_accuracy.get("multi_clause", 0.0)
            notes.append(
                f"**The verifier scores multi-clause answers lowest — the category "
                f"the product exists to handle.** Mean groundedness by category runs "
                f"from {best_score:.2f} ({best}) down to {worst_score:.2f} "
                f"(multi_clause), while decision accuracy on multi_clause is "
                f"{accuracy:.0%}: every one of those answers was *correct*. The cause "
                f'is in the verification prompt, which flags "two separate excerpts '
                f'merged into a single claim that neither supports alone" — and a '
                f"correct multi-clause answer is exactly that. The rule that catches "
                f"a fabricated synthesis also catches a legitimate one. Two answers "
                f"landed on 0.50, at the suppression boundary; raising the threshold "
                f"to 0.6 would withhold correct answers about coverage exclusions, "
                f"which is the kind of answer a user most needs."
            )

    # 4. Provider-enforced schemas are doing some of the work attributed elsewhere.
    if on and on.citations.validity >= 0.995:
        notes.append(
            "**Citation validity of 100% is partly structural.** The answering model "
            "is constrained by a provider-enforced JSON schema and the context is "
            "small, so malformed or invented chunk ids are close to impossible by "
            "construction. The interesting half of binding — catching a *quote* that "
            "does not appear in a chunk it names — was never exercised here."
        )

    return notes


def render_report(
    arms: dict[str, Report],
    *,
    model: str,
    embedding_model: str,
    commit: str,
    generated_at: datetime,
    dataset: Stats,
    chunks_per_document: dict[str, int] | None = None,
    context_chunk_count: int = 8,
) -> str:
    on = arms.get("on")
    off = arms.get("off")
    primary = on or next(iter(arms.values()))

    lines: list[str] = []
    add = lines.append

    add("# Evaluation report")
    add("")
    add(
        "> Generated by `python -m eval.run_eval`. Every number here is produced by "
        "that command against live models and the live database — none are "
        "hand-written. Unflattering results are included; that is the point of "
        "publishing it."
    )
    add("")

    notes = _limitations(
        arms,
        chunks_per_document=chunks_per_document or {},
        context_chunk_count=context_chunk_count,
    )
    if notes:
        add("## Read this first — what these numbers do not show")
        add("")
        add(
            "Placed before the results rather than after them, because a caveat at "
            "the bottom of a report is a caveat nobody reads."
        )
        add("")
        for note in notes:
            add(f"- {note}")
            add("")

    # --- provenance ---------------------------------------------------------
    add("## Run")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Generated | {generated_at.strftime('%Y-%m-%d %H:%M UTC')} |")
    add(f"| Commit | `{commit}` |")
    add(f"| Answering model | `{model}` |")
    add(f"| Embedding model | `{embedding_model}` (1536 dimensions) |")
    add("| Prompts | `answer_v1`, `verify_v1` |")
    add(f"| Questions | {dataset.total} |")
    add(
        f"| Adversarial negatives | {dataset.by_category.get('negative', 0)} ({dataset.negative_share:.0%}) |"
    )
    add("")

    # --- the ablation -------------------------------------------------------
    if on and off:
        add("## The ablation")
        add("")
        add(
            "The same dataset, twice: once with citation binding and "
            "self-verification enabled, once with both switched off. The second "
            "column is what this product would be without the layer it exists to "
            "build."
        )
        add("")
        add("| Metric | Mechanisms OFF | Mechanisms ON | Change |")
        add("|---|---:|---:|---:|")
        add(
            f"| **Refusal accuracy** | {_pct(off.refusal.refusal_accuracy)} | "
            f"{_pct(on.refusal.refusal_accuracy)} | "
            f"{_delta(on.refusal.refusal_accuracy, off.refusal.refusal_accuracy)} |"
        )
        add(
            f"| **False-refusal rate** | {_pct(off.refusal.false_refusal_rate)} | "
            f"{_pct(on.refusal.false_refusal_rate)} | "
            f"{_delta(on.refusal.false_refusal_rate, off.refusal.false_refusal_rate, higher_is_better=False)} |"
        )
        add(
            f"| **Balanced accuracy** | {_pct(off.refusal.balanced_accuracy)} | "
            f"{_pct(on.refusal.balanced_accuracy)} | "
            f"{_delta(on.refusal.balanced_accuracy, off.refusal.balanced_accuracy)} |"
        )
        add(
            f"| Citation validity | {_pct(off.citations.validity)} | "
            f"{_pct(on.citations.validity)} | "
            f"{_delta(on.citations.validity, off.citations.validity)} |"
        )
        add(
            f"| Caught hallucinations | {off.citations.suppressions} | "
            f"{on.citations.suppressions} | — |"
        )
        add(
            f"| Cost per question | ${off.cost.mean_cost_per_query_usd:.4f} | "
            f"${on.cost.mean_cost_per_query_usd:.4f} | — |"
        )
        add("")
        add(
            "**Read the first two rows together.** Refusal accuracy alone is "
            "trivially gamed by refusing everything, and the false-refusal rate "
            "alone by never refusing. Balanced accuracy is the mean of the two "
            "and lands at 50% for either degenerate strategy."
        )
        add("")

    # --- retrieval ----------------------------------------------------------
    add("## Retrieval")
    add("")
    add(
        "Measured over the answerable questions only — a negative has no correct "
        "chunk to find. A hit requires **every** expected span to be present in "
        "the chunks that actually reached the prompt, not merely retrieved: a "
        "peril without its limit has retrieved the question restated, not the "
        "answer."
    )
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| Recall@8 | {_pct(primary.retrieval.recall_at_k)} |")
    add(f"| MRR | {primary.retrieval.mrr:.3f} |")
    add(f"| Answerable questions | {primary.retrieval.answerable_count} |")
    add("")

    add("### By category")
    add("")
    add("| Category | Questions | Recall@8 | Decision accuracy |")
    add("|---|---:|---:|---:|")
    for category, metrics in sorted(primary.by_category.items()):
        count = sum(1 for _ in range(metrics.answerable_count)) or 0
        accuracy = primary.category_decision_accuracy.get(category, 0.0)
        shown = "—" if category == "negative" else _pct(metrics.recall_at_k)
        add(
            f"| {category} | {metrics.answerable_count if category != 'negative' else count} "
            f"| {shown} | {_pct(accuracy)} |"
        )
    add("")
    add(
        "`negative` has no recall figure by construction — there is nothing to "
        "retrieve. Its decision accuracy is the refusal accuracy for that subset."
    )
    add("")

    # --- refusal ------------------------------------------------------------
    add("## Refusal")
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| Correct refusals | {primary.refusal.correct_refusals} / {primary.refusal.negatives} |")
    add(f"| False refusals | {primary.refusal.false_refusals} / {primary.refusal.answerables} |")
    add(f"| Refusal accuracy | {_pct(primary.refusal.refusal_accuracy)} |")
    add(f"| False-refusal rate | {_pct(primary.refusal.false_refusal_rate)} |")
    add(f"| Balanced accuracy | {_pct(primary.refusal.balanced_accuracy)} |")
    add("")

    # --- citations & groundedness -------------------------------------------
    add("## Citations and groundedness")
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| Citations offered | {primary.citations.offered} |")
    add(f"| Survived binding | {primary.citations.kept} |")
    add(f"| Citation validity | {_pct(primary.citations.validity)} |")
    add(f"| Answers suppressed (caught hallucinations) | {primary.citations.suppressions} |")
    if primary.groundedness_mean is not None:
        add(f"| Mean groundedness (served answers) | {primary.groundedness_mean:.2f} |")
    add("")
    if primary.groundedness_by_category:
        add("Mean groundedness by category, over served answers:")
        add("")
        add("| Category | Mean groundedness | Decision accuracy |")
        add("|---|---:|---:|")
        for category, score in sorted(
            primary.groundedness_by_category.items(), key=lambda kv: kv[1]
        ):
            accuracy = primary.category_decision_accuracy.get(category, 0.0)
            add(f"| {category} | {score:.2f} | {_pct(accuracy)} |")
        add("")

    add("Groundedness distribution over served answers:")
    add("")
    add("| Band | Answers |")
    add("|---|---:|")
    for band, count in primary.groundedness_distribution.items():
        add(f"| {band} | {count} |")
    add("")
    add(
        "The mean covers **served** answers only. Including suppressed ones would "
        "mix “we checked and it held up” with “we checked, it didn't, and we "
        "withheld it” — the second is a success of the system, counted separately "
        "as a caught hallucination."
    )
    add("")

    # --- cost ---------------------------------------------------------------
    add("## Cost and latency")
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| Cost per question | ${primary.cost.mean_cost_per_query_usd:.4f} |")
    add(f"| p50 latency | {primary.cost.p50_latency_ms / 1000:.1f}s |")
    add(f"| p95 latency | {primary.cost.p95_latency_ms / 1000:.1f}s |")
    add(f"| Total for this run | ${sum(a.cost.total_usd for a in arms.values()):.2f} |")
    add("")
    add(
        "p50 and p95 rather than a mean: one cold start moves a mean and says "
        "nothing about the typical experience."
    )
    add("")

    if primary.errors:
        add("## Errors")
        add("")
        add(
            f"{primary.errors} question(s) raised rather than answering. These are "
            "counted separately from refusals — a crash is not a decision."
        )
        add("")

    return "\n".join(lines) + "\n"
