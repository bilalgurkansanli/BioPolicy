"use client";

import { useEffect, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { fetchSpend } from "@/lib/api";
import type { Spend } from "@/lib/types";

/**
 * What the demo has actually cost, live.
 *
 * The report publishes what one evaluation run cost under controlled
 * conditions. This is the other number — what the thing has spent serving real
 * questions from real visitors — and it is the one a reader cannot check any
 * other way.
 *
 * It is deliberately allowed to be unflattering. A demo that has burned most of
 * its budget says so here before it says so by refusing everybody.
 */
export function SpendCounter() {
  const { t } = useLocale();
  const [spend, setSpend] = useState<Spend | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchSpend(controller.signal)
      .then((result) => {
        setSpend(result);
        setFailed(false);
      })
      .catch((error: unknown) => {
        // An abort is not a failure. React runs effects twice in development
        // and a fast navigation aborts in production, so treating it as one
        // latches the component into rendering nothing — permanently, because
        // the retry that follows can set the data but never clears the flag.
        if ((error as Error).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);

  // Nothing rather than a skeleton: this sits under a report full of real
  // numbers, and a shimmering placeholder among them reads as one of them.
  if (failed || !spend) return null;

  const used = spend.budget_usd > 0 ? spend.total_usd / spend.budget_usd : 0;

  return (
    <section className="mt-10 rounded-xl border border-line bg-surface p-5">
      <h2 className="text-sm font-medium text-ink">{t.evaluation.spendTitle}</h2>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        <Figure
          value={`$${spend.total_usd.toFixed(2)}`}
          label={t.evaluation.spendTotal}
        />
        <Figure
          value={
            spend.per_question_usd === null
              ? "—"
              : `$${spend.per_question_usd.toFixed(4)}`
          }
          label={t.evaluation.spendPerQuestion}
        />
        <Figure value={String(spend.questions)} label={t.evaluation.spendQuestions} />
        <Figure
          value={`$${spend.budget_usd.toFixed(0)}`}
          label={t.evaluation.spendBudget}
        />
      </dl>

      <div className="mt-5 h-1 w-full overflow-hidden rounded-full bg-line">
        <div
          className={`h-full ${used >= 1 ? "bg-danger" : used >= 0.8 ? "bg-refuse" : "bg-good"}`}
          style={{ width: `${Math.min(100, Math.round(used * 100))}%` }}
        />
      </div>

      <p className="mt-3 text-xs leading-5 text-ink-faint">
        {/* The caveat is not a footnote. A cost figure that silently covers only
            part of the traffic is a cost figure that understates itself. */}
        {t.evaluation.spendCaveat.replace(
          "{share}",
          `${Math.round(spend.priced_share * 100)}%`,
        )}
      </p>
    </section>
  );
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <dd className="font-mono text-xl font-medium tabular-nums text-ink">
        {value}
      </dd>
      <dt className="mt-0.5 text-xs text-ink-muted">{label}</dt>
    </div>
  );
}
