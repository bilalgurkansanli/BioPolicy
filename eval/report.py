"""Render the evaluation report, in either language it is read in.

Formatting only — every number comes from `eval/metrics.py`. Kept separate so
the arithmetic can be tested without a Markdown fixture, and so changing the
presentation cannot accidentally change a result.

The report is written to be read by someone sceptical. That means the
unflattering numbers appear beside the flattering ones rather than in a
footnote, and any metric that can be gamed is shown next to the metric that
exposes the gaming.

The sentences themselves live in `eval/copy.py`, one object per sentence with
both languages inside it. This module decides *which* sentence applies and what
numbers go into it; that one knows how to say it. The split is what makes the
two languages the same report rather than two reports about the same run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from api.constants import EMBEDDING_DIM
from api.generation import prompts
from api.retrieval.floor import FLOOR_DISTANCE, FLOOR_MODEL
from eval.copy import ARM_LABELS, Lang, T
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
    lang: Lang,
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
        notes.append(
            T.recall_not_meaningful.format(
                lang,
                smallest=min(chunks_per_document.values()),
                biggest=max(chunks_per_document.values()),
                context=context_chunk_count,
            )
        )

    # 1b. Provider failures, because they are indistinguishable from refusals.
    errored = {name: report.errors for name, report in arms.items() if report.errors}
    if errored:
        notes.append(
            T.provider_errors.format(
                lang,
                total=sum(errored.values()),
                arms=", ".join(f"`{name}` ({count})" for name, count in sorted(errored.items())),
            )
        )

    # 1c. Does the fourth mechanism earn its call?
    strict_ent, guarded = arms.get("strict_entailed"), arms.get("strict_guarded")
    if strict_ent and guarded:
        caught = strict_ent.refusal.refusal_accuracy - guarded.refusal.refusal_accuracy
        cost_in_false = strict_ent.refusal.false_refusal_rate - guarded.refusal.false_refusal_rate
        extra = (
            strict_ent.cost.mean_cost_per_query_usd / guarded.cost.mean_cost_per_query_usd - 1
            if guarded.cost.mean_cost_per_query_usd
            else 0.0
        )
        notes.append(
            T.entailment_did_not_deliver.format(
                lang,
                caught=f"{caught:+.0%}",
                false_refusal=f"{cost_in_false:+.0%}",
                extra=f"{extra:.0%}",
            )
        )

    # 2. Which lever actually moved the numbers?
    naive_only, naive_guarded = arms.get("naive_only"), arms.get("naive_guarded")
    strict_only, strict_guarded = arms.get("strict_only"), arms.get("strict_guarded")

    if naive_only and naive_guarded and strict_only and strict_guarded:
        prompt_effect = strict_only.refusal.balanced_accuracy - naive_only.refusal.balanced_accuracy
        mechanism_effect = (
            naive_guarded.refusal.balanced_accuracy - naive_only.refusal.balanced_accuracy
        )
        overhead = (
            strict_guarded.cost.mean_cost_per_query_usd / strict_only.cost.mean_cost_per_query_usd
            - 1
            if strict_only.cost.mean_cost_per_query_usd
            else 0.0
        )

        if abs(mechanism_effect) < 0.005 and prompt_effect >= 0.01:
            notes.append(
                T.prompt_did_the_work.format(
                    lang,
                    mechanism_effect=f"{mechanism_effect:+.0%}",
                    prompt_effect=f"{prompt_effect:+.0%}",
                    overhead=f"{overhead:.0%}",
                )
            )

    # 3. The verifier does not treat every kind of answer alike.
    primary = arms.get("strict_guarded") or next(iter(arms.values()))
    scores = primary.groundedness_by_category
    if len(scores) >= 3:
        worst, worst_score = min(scores.items(), key=lambda kv: kv[1])
        best, best_score = max(scores.items(), key=lambda kv: kv[1])
        if worst == "multi_clause" and best_score - worst_score >= 0.1:
            notes.append(
                T.verifier_multi_clause.format(
                    lang,
                    best=best,
                    best_score=f"{best_score:.2f}",
                    worst_score=f"{worst_score:.2f}",
                    accuracy=_pct(primary.category_decision_accuracy.get("multi_clause", 0.0)),
                )
            )

    # 4. Provider-enforced schemas are doing some of the work attributed elsewhere.
    if (on := arms.get("strict_guarded")) and on.citations.validity >= 0.995:
        notes.append(T.citation_validity_structural.of(lang))

    return notes


def _render_floor(add: Callable[[str], None], bands: list[dict[str, Any]], *, lang: Lang) -> None:
    """The floor's own measurement, which the answering run does not produce.

    It comes from `eval.measure_floor` — embedding calls only, over populations
    the golden set has no schema for (a question about football has no expected
    answer and no evidence spans). Rendered here anyway, because a threshold
    published without the distribution it was derived from is a magic number.

    The threshold and the model it was measured against are printed with it, and
    that is not decoration. This section reported the distribution and never the
    number, so when the store moved from `gemini-embedding-001` to
    `voyage-4-lite` the constant stayed at a value belonging to a vector space
    that no longer existed — and every report published in between looked
    exactly the same. A published threshold that does not name its space cannot
    be checked by the person reading it.
    """
    add(T.floor_heading.of(lang))
    add("")
    add(T.floor_intro.of(lang))
    add("")
    add(
        T.floor_threshold.of(lang)
        .replace("{threshold}", f"{FLOOR_DISTANCE}")
        .replace("{model}", f"`{FLOOR_MODEL}`")
    )
    add("")
    add(f"| {T.floor_population.of(lang)} | n | min | median | max | {T.floor_refused.of(lang)} |")
    add("|---|---:|---:|---:|---:|---:|")
    for band in bands:
        if not band.get("n"):
            continue
        label = T.floor_bands.get(band["band"])
        name = label.of(lang) if label else band["band"]
        add(
            f"| {name} | {band['n']} | {band['min']:.4f} | {band['median']:.4f} "
            f"| {band['max']:.4f} | {band['fired']} / {band['n']} |"
        )
    add("")
    add(T.floor_finding.of(lang))
    add("")


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
    floor: list[dict[str, Any]] | None = None,
    lang: Lang = "en",
) -> str:
    primary = arms.get("strict_guarded") or next(iter(arms.values()))
    baseline = arms.get("naive_only")

    lines: list[str] = []
    add = lines.append

    add(T.title.of(lang))
    add("")
    add(T.generated_by.of(lang))
    add("")

    notes = _limitations(
        arms,
        chunks_per_document=chunks_per_document or {},
        context_chunk_count=context_chunk_count,
        lang=lang,
    )
    if notes:
        add(T.caveats_heading.of(lang))
        add("")
        add(T.caveats_intro.of(lang))
        add("")
        for note in notes:
            add(f"- {note}")
            add("")

    # --- provenance ---------------------------------------------------------
    add(T.run_heading.of(lang))
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| {T.row_generated.of(lang)} | {generated_at.strftime('%Y-%m-%d %H:%M UTC')} |")
    add(f"| {T.row_commit.of(lang)} | `{commit}` |")
    add(f"| {T.row_answering_model.of(lang)} | `{model}` |")
    add(
        f"| {T.row_embedding_model.of(lang)} | `{embedding_model}` ({T.dimensions.format(lang, dims=EMBEDDING_DIM)}) |"
    )
    # Read from the module rather than written here. A report that hard-codes
    # its own prompt version keeps printing the old one the day the prompt
    # changes, which is the single most misleading thing this table could do.
    add(f"| {T.row_prompts.of(lang)} | `{prompts.ANSWER}`, `{prompts.VERIFY}` |")
    add(f"| {T.row_questions.of(lang)} | {dataset.total} |")
    add(
        f"| {T.row_negatives.of(lang)} | {dataset.by_category.get('negative', 0)} "
        f"({dataset.negative_share:.0%}) |"
    )
    add("")

    # --- the injection set --------------------------------------------------
    # Placed above the ablation because when this section exists it is the whole
    # reason the run happened, and because its verdict is binary in a way the
    # rest of the report is not: an obeyed instruction is not a percentage point.
    if primary.injection:
        add(T.injection_heading.of(lang))
        add("")
        add(T.injection_intro.of(lang))
        add("")
        add(T.injection_table_header.of(lang))
        add("|---|---:|---:|---:|---:|")
        for name, arm in arms.items():
            inj = arm.injection
            if inj is None:
                continue
            add(
                f"| `{name}` | {inj.attacks} | **{inj.obeyed}** | "
                f"{_pct(inj.block_rate)} | {inj.refused} |"
            )
        add("")
        add(T.injection_per_technique.of(lang))
        add("")
        add(T.injection_technique_header.of(lang))
        add("|---|---|")
        for technique, obeyed in sorted(primary.injection.by_technique.items()):
            mark = T.yes.of(lang) if obeyed else T.no.of(lang)
            add(f"| `{technique}` | {mark} |")
        add("")
        add(T.injection_single_observations.of(lang))
        add("")

    # --- the ablation -------------------------------------------------------
    if len(arms) > 1:
        add(T.ablation_heading.of(lang))
        add("")
        add(T.ablation_intro.of(lang))
        add("")
        add(T.naive_not_strawman.of(lang))
        add("")
        add(T.ablation_table_header.of(lang))
        add("|---|---:|---:|---:|---:|---:|---:|")
        for key, label in ARM_LABELS.items():
            report = arms.get(key)
            if report is None:
                continue
            add(
                f"| {label.of(lang)} "
                f"| {_pct(report.refusal.refusal_accuracy)} "
                f"| {_pct(report.refusal.false_refusal_rate)} "
                f"| {_pct(report.refusal.balanced_accuracy)} "
                f"| {_pct(report.citations.validity)} "
                f"| {report.citations.suppressions} "
                f"| ${report.cost.mean_cost_per_query_usd:.4f} |"
            )
        add("")
        if baseline:
            add(
                T.baseline_to_shipped.format(
                    lang,
                    base_balanced=_pct(baseline.refusal.balanced_accuracy),
                    ship_balanced=_pct(primary.refusal.balanced_accuracy),
                    base_refusal=_pct(baseline.refusal.refusal_accuracy),
                    ship_refusal=_pct(primary.refusal.refusal_accuracy),
                )
            )
            add("")
        add(T.read_together.of(lang))
        add("")
        add(T.comparing_rows.of(lang))
        add("")

    # --- retrieval ----------------------------------------------------------
    add(T.retrieval_heading.of(lang))
    add("")
    add(T.retrieval_intro.of(lang))
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| {T.row_recall.of(lang)} | {_pct(primary.retrieval.recall_at_k)} |")
    add(f"| {T.row_mrr.of(lang)} | {primary.retrieval.mrr:.3f} |")
    add(f"| {T.row_answerable.of(lang)} | {primary.retrieval.answerable_count} |")
    add("")

    add(T.by_category_heading.of(lang))
    add("")
    add(T.by_category_header.of(lang))
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
    add(T.negative_has_no_recall.of(lang))
    add("")

    # --- refusal ------------------------------------------------------------
    add(T.refusal_heading.of(lang))
    add("")
    add("| | |")
    add("|---|---:|")
    add(
        f"| {T.row_correct_refusals.of(lang)} | "
        f"{primary.refusal.correct_refusals} / {primary.refusal.negatives} |"
    )
    add(
        f"| {T.row_false_refusals.of(lang)} | "
        f"{primary.refusal.false_refusals} / {primary.refusal.answerables} |"
    )
    add(f"| {T.row_refusal_accuracy.of(lang)} | {_pct(primary.refusal.refusal_accuracy)} |")
    add(f"| {T.row_false_refusal_rate.of(lang)} | {_pct(primary.refusal.false_refusal_rate)} |")
    add(f"| {T.row_balanced.of(lang)} | {_pct(primary.refusal.balanced_accuracy)} |")
    add("")

    if floor is not None:
        _render_floor(add, floor, lang=lang)

    # --- citations & groundedness -------------------------------------------
    add(T.citations_heading.of(lang))
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| {T.row_offered.of(lang)} | {primary.citations.offered} |")
    add(f"| {T.row_kept.of(lang)} | {primary.citations.kept} |")
    add(f"| {T.row_validity.of(lang)} | {_pct(primary.citations.validity)} |")
    add(f"| {T.row_suppressed.of(lang)} | {primary.citations.suppressions} |")
    if primary.groundedness_mean is not None:
        add(f"| {T.row_mean_groundedness.of(lang)} | {primary.groundedness_mean:.2f} |")
    add("")
    if primary.groundedness_by_category:
        add(T.groundedness_by_category.of(lang))
        add("")
        add(T.groundedness_category_header.of(lang))
        add("|---|---:|---:|")
        for category, score in sorted(
            primary.groundedness_by_category.items(), key=lambda kv: kv[1]
        ):
            accuracy = primary.category_decision_accuracy.get(category, 0.0)
            add(f"| {category} | {score:.2f} | {_pct(accuracy)} |")
        add("")

    add(T.groundedness_distribution.of(lang))
    add("")
    add(T.distribution_header.of(lang))
    add("|---|---:|")
    for band, count in primary.groundedness_distribution.items():
        add(f"| {band} | {count} |")
    add("")
    add(T.mean_covers_served.of(lang))
    add("")

    # --- cost ---------------------------------------------------------------
    add(T.cost_heading.of(lang))
    add("")
    add("| | |")
    add("|---|---:|")
    add(f"| {T.row_cost_per_question.of(lang)} | ${primary.cost.mean_cost_per_query_usd:.4f} |")
    add(f"| {T.row_p50.of(lang)} | {primary.cost.p50_latency_ms / 1000:.1f}s |")
    add(f"| {T.row_p95.of(lang)} | {primary.cost.p95_latency_ms / 1000:.1f}s |")
    add(f"| {T.row_total.of(lang)} | ${sum(a.cost.total_usd for a in arms.values()):.2f} |")
    add("")
    add(T.percentiles_not_mean.of(lang))
    add("")

    if primary.errors:
        add(T.errors_heading.of(lang))
        add("")
        add(T.errors_body.format(lang, count=primary.errors))
        add("")

    return "\n".join(lines) + "\n"
