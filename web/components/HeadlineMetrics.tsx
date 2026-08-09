"use client";

import { useLocale } from "@/components/LocaleProvider";
import type { HistoryRow } from "@/components/MetricHistory";

/**
 * The four numbers, before the report that explains them.
 *
 * The page used to open with two full reports rendered end to end — 250 lines
 * of Markdown, most of it internal reasoning about ablation arms. Everything a
 * visitor came for was in it and none of it was visible without scrolling past
 * an argument about whether the entailment check earns its call.
 *
 * Nothing was deleted to fix that. The report is still on the page, still
 * verbatim, still including the parts that do not flatter the system — it is
 * just no longer the first thing, and no longer open by default.
 *
 * ## Why these four
 *
 * Refusal accuracy and false-refusal rate are shown **together, always**. Either
 * alone is trivially gamed: a system that refuses everything scores 100% on the
 * first, one that never refuses scores 0% on the second, and neither is a
 * working product. `eval/metrics.py` makes the same argument at more length.
 *
 * Recall says whether retrieval put the answer in front of the model at all,
 * and citation validity says whether the quotes it gave back were real. Those
 * four bound the claim this project makes; cost belongs in the line underneath
 * rather than in a card, because it is context rather than a result.
 */
export function HeadlineMetrics({ rows }: { rows: HistoryRow[] }) {
  const { t, locale } = useLocale();

  // The shipped configuration, not merely the latest run. History collects
  // every ablation arm, and the most recent line is whichever one happened to
  // be measured last — `strict_entailed` at the time of writing, which is the
  // arm this deployment does *not* run. Publishing that as "the numbers" would
  // be quoting an experiment as a result.
  const shipped = [...rows]
    .reverse()
    .find((row) => row.set === "demo" && row.arm === "strict_guarded");
  if (!shipped) return null;

  const percent = (value: number) =>
    new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-GB", {
      style: "percent",
      maximumFractionDigits: 0,
    }).format(value);

  const cards = [
    {
      label: t.evaluation.cards.refusalAccuracy,
      value: percent(shipped.refusal_accuracy),
      note: t.evaluation.cards.refusalAccuracyNote,
      good: true,
    },
    {
      label: t.evaluation.cards.falseRefusal,
      value: percent(shipped.false_refusal_rate),
      note: t.evaluation.cards.falseRefusalNote,
      good: false,
    },
    {
      label: t.evaluation.cards.recall,
      value: percent(shipped.recall_at_k ?? 0),
      note: t.evaluation.cards.recallNote,
      good: true,
    },
    {
      label: t.evaluation.cards.citationValidity,
      value: percent(shipped.citation_validity ?? 0),
      note: t.evaluation.cards.citationValidityNote,
      good: true,
    },
  ];

  return (
    <section className="mt-8">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-line bg-surface p-3.5"
          >
            <dt className="text-[11px] leading-4 text-ink-faint">
              {card.label}
            </dt>
            <dd
              className={`mt-1.5 font-mono text-2xl tabular-nums ${
                card.good ? "text-ink" : "text-ink"
              }`}
            >
              {card.value}
            </dd>
            <p className="mt-1 text-[11px] leading-4 text-ink-faint">
              {card.note}
            </p>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-xs leading-5 text-ink-faint">
        {t.evaluation.cards.footnote
          .replace("{questions}", String(shipped.questions))
          .replace("{cost}", shipped.cost_per_question.toFixed(4))
          .replace("{commit}", shipped.commit)}
      </p>
    </section>
  );
}
