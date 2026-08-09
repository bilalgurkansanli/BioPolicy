"use client";

import { useLocale } from "@/components/LocaleProvider";

/**
 * How the headline numbers have moved across evaluation runs.
 *
 * The report is a photograph: it says what was true the day it was rendered and
 * nothing about whether a figure moved because of a change or because the model
 * had a different afternoon. This is the record that tells those apart.
 *
 * It draws only the shipped arm. Plotting all six would put the deliberately
 * bad baselines on the same axes as the shipped configuration, which makes the
 * chart look like a system that keeps regressing.
 */
export type HistoryRow = {
  run_at: string;
  commit: string;
  set: string;
  arm: string;
  questions: number;
  refusal_accuracy: number;
  false_refusal_rate: number;
  balanced_accuracy: number;
  cost_per_question: number;
  // Written by every run but not charted — the chart tracks the two refusal
  // numbers over time, while these two are read once, for the current
  // configuration, by `HeadlineMetrics`. Optional because rows appended before
  // they were recorded are still valid history.
  recall_at_k?: number;
  citation_validity?: number;
};

const SERIES = [
  { key: "balanced_accuracy", color: "var(--good)" },
  { key: "refusal_accuracy", color: "var(--accent)" },
  { key: "false_refusal_rate", color: "var(--danger)" },
] as const;

export function MetricHistory({ rows }: { rows: HistoryRow[] }) {
  const { t } = useLocale();

  const shipped = rows.filter((row) => row.arm === "strict_guarded" && row.set === "demo");

  // One point is not a trend, and drawing a chart through it would imply one.
  if (shipped.length < 2) {
    return (
      <section className="mt-10 rounded-xl border border-line bg-surface p-5">
        <h2 className="text-sm font-medium text-ink">{t.evaluation.historyTitle}</h2>
        <p className="mt-2 text-xs leading-5 text-ink-faint">
          {shipped.length === 0
            ? t.evaluation.historyEmpty
            : t.evaluation.historyTooShort}
        </p>
      </section>
    );
  }

  const width = 640;
  const height = 140;
  const pad = { top: 12, right: 12, bottom: 22, left: 34 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;

  const x = (index: number) =>
    pad.left + (shipped.length === 1 ? plotWidth / 2 : (index / (shipped.length - 1)) * plotWidth);
  // Fixed 0–100 axis rather than fitted: an axis that rescales itself turns a
  // one-point wobble into a cliff, which is the most common way a metric chart
  // lies without anyone intending it to.
  const y = (value: number) => pad.top + (1 - value) * plotHeight;

  return (
    <section className="mt-10 rounded-xl border border-line bg-surface p-5">
      <h2 className="text-sm font-medium text-ink">{t.evaluation.historyTitle}</h2>
      <p className="mt-1 text-xs text-ink-faint">{t.evaluation.historyNote}</p>

      <div className="mt-4 overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full min-w-[420px]"
          role="img"
          aria-label={t.evaluation.historyTitle}
        >
          {[0, 0.5, 1].map((tick) => (
            <g key={tick}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--line)"
                strokeWidth="1"
              />
              <text
                x={pad.left - 6}
                y={y(tick) + 3}
                textAnchor="end"
                className="fill-[var(--ink-faint)] text-[9px]"
              >
                {Math.round(tick * 100)}%
              </text>
            </g>
          ))}

          {SERIES.map((series) => (
            <polyline
              key={series.key}
              fill="none"
              stroke={series.color}
              strokeWidth="2"
              strokeLinejoin="round"
              points={shipped
                .map((row, index) => `${x(index)},${y(row[series.key])}`)
                .join(" ")}
            />
          ))}

          {shipped.map((row, index) => (
            <text
              key={row.run_at}
              x={x(index)}
              y={height - 6}
              textAnchor="middle"
              className="fill-[var(--ink-faint)] font-mono text-[9px]"
            >
              {row.commit.slice(0, 7)}
            </text>
          ))}
        </svg>
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-muted">
        {SERIES.map((series) => (
          <li key={series.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-0.5 w-4 rounded-full"
              style={{ backgroundColor: series.color }}
            />
            {t.evaluation.historySeries[series.key]}
          </li>
        ))}
      </ul>
    </section>
  );
}
