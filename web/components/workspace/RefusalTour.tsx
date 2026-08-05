"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";

/**
 * Thirty seconds of the product's actual claim, without spending a question.
 *
 * The problem this solves is specific. A visitor arrives with three questions,
 * asks three easy ones, gets three good answers, and leaves having seen a
 * competent document search — which is not what this project is about. The
 * thing worth seeing is the refusal, and nobody spends a scarce question trying
 * to make software fail.
 *
 * ## Why it is a recording and not a live call
 *
 * A live "watch it refuse" button would either burn one of the three questions
 * or need a hidden allowance, and a hidden allowance is a hole in the limit the
 * rest of the system is careful about.
 *
 * The trade is that a recording is not evidence — a screenshot of a passing
 * test proves nothing. So it is labelled as a recording, and it links to the
 * evaluation, where the same behaviour is measured over seventy questions
 * rather than demonstrated over one. The demonstration is for understanding;
 * the report is for believing.
 */
type Step = {
  title: string;
  body: string;
  quote?: string;
  tone: "asked" | "found" | "refused";
};

export function RefusalTour() {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  const steps: Step[] = [
    { tone: "asked", title: t.tour.step1Title, body: t.tour.step1Body },
    {
      tone: "found",
      title: t.tour.step2Title,
      body: t.tour.step2Body,
      quote: t.tour.step2Quote,
    },
    { tone: "refused", title: t.tour.step3Title, body: t.tour.step3Body },
  ];

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setStep(0);
          setOpen(true);
        }}
        className="mt-4 inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-surface-sunken"
      >
        <span aria-hidden>▷</span>
        {t.tour.start}
      </button>
    );
  }

  const current = steps[step];
  const last = step === steps.length - 1;

  return (
    <div className="mt-4 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
          {t.tour.label} · {step + 1}/{steps.length}
        </span>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded px-1.5 py-0.5 text-[11px] text-ink-faint transition-colors hover:text-ink"
        >
          {t.tour.close}
        </button>
      </div>

      <h4
        className={`mt-2 text-sm font-semibold ${
          current.tone === "refused" ? "text-refuse" : "text-ink"
        }`}
      >
        {current.title}
      </h4>
      <p className="mt-1.5 text-sm leading-6 text-ink-muted">{current.body}</p>

      {current.quote && (
        <p className="mt-2 rounded-lg border border-line bg-surface-sunken px-2.5 py-2 text-xs leading-5 text-ink">
          “{current.quote}”
        </p>
      )}

      <div className="mt-4 flex items-center gap-2">
        {!last ? (
          <button
            type="button"
            onClick={() => setStep((value) => value + 1)}
            className="rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-paper"
          >
            {t.tour.next}
          </button>
        ) : (
          <a
            href="/eval"
            className="rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-paper"
          >
            {t.tour.toEval}
          </a>
        )}
        <span className="text-[11px] text-ink-faint">{t.tour.recorded}</span>
      </div>
    </div>
  );
}
