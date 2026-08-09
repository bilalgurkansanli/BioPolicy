"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { HeadlineMetrics } from "@/components/HeadlineMetrics";
import { useLocale } from "@/components/LocaleProvider";
import { MetricHistory, type HistoryRow } from "@/components/MetricHistory";
import { SpendCounter } from "@/components/SpendCounter";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

/** One report, as written by the tool, in each language it writes it in. */
type Rendered = { en: string | null; tr: string | null };

/**
 * A report, folded away until asked for.
 *
 * `<details>` rather than a React toggle: it is keyboard-operable, it is in the
 * accessibility tree as a disclosure without any ARIA, and a reader who prints
 * the page or searches it with the browser's own find can still reach the text
 * inside. None of that is true of a `useState` that unmounts its content.
 */
function Details({
  summary,
  note,
  children,
}: {
  summary: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group mt-8 border-t border-line pt-6">
      <summary className="flex cursor-pointer list-none items-baseline gap-2 text-sm font-medium text-ink marker:content-none">
        <span
          aria-hidden
          className="font-mono text-xs text-ink-faint transition-transform group-open:rotate-90"
        >
          ›
        </span>
        {summary}
      </summary>
      <p className="mt-1.5 pl-5 text-xs leading-5 text-ink-faint">{note}</p>
      <div className="report mt-5 overflow-x-auto">{children}</div>
    </details>
  );
}

/**
 * The report is not translated here — it arrives already written in both
 * languages by `python -m eval.run_eval`, from one run and one set of numbers
 * (see `eval/copy.py`). This page only picks the file that matches the reader,
 * so what is shown is still verbatim: the tool's own words, in the tool's own
 * two languages.
 *
 * English is the fallback when a Turkish file has not been generated yet. A
 * report in the wrong language is readable; a missing one is not.
 */
export function EvaluationReport({
  markdown,
  hard,
  history,
}: {
  markdown: Rendered;
  /** The adversarial set, reported separately so its numbers cannot be read as
      the demo's. */
  hard: Rendered;
  history: HistoryRow[];
}) {
  const { locale, t } = useLocale();
  const pick = (rendered: Rendered) =>
    (locale === "tr" ? rendered.tr : rendered.en) ?? rendered.en;
  const report = pick(markdown);
  const adversarial = pick(hard);

  return (
    <>
      <SiteHeader />
      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl px-4 py-12 sm:px-6">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            {t.evaluation.title}
          </h1>
          <p className="mt-3 text-sm leading-6 text-ink-muted">
            {t.evaluation.lede}
          </p>

          {/* Only when the reader is looking at a language the report was not
              written in — which now means only when the Turkish file has not
              been generated. Left in place because that state is real, and an
              English page with no explanation reads as a bug. */}
          {locale === "tr" && markdown.tr === null && (
            <p className="mt-4 rounded-xl border border-line bg-surface-sunken px-4 py-3 text-xs leading-5 text-ink-faint">
              {t.evaluation.languageNote}
            </p>
          )}

          <HeadlineMetrics rows={history} />

          {/* The one caveat that changes how the numbers above should be read,
              stated here rather than left for whoever opens the full report.
              The rest of the qualifications are in it, at length. */}
          <p className="mt-6 rounded-xl border border-line bg-surface-sunken px-4 py-3 text-xs leading-5 text-ink-muted">
            {t.evaluation.caveat}
          </p>

          <SpendCounter />
          <MetricHistory rows={history} />

          {report === null ? (
            <p className="mt-10 rounded-xl border border-line bg-surface p-4 text-sm text-ink-muted">
              {t.evaluation.missing}
            </p>
          ) : (
            <Details summary={t.evaluation.fullReport} note={t.evaluation.fullReportNote}>
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // The report opens with its own `# Evaluation report`, which
                  // would be a second page-level heading. Demoted rather than
                  // stripped: the file is rendered as written.
                  h1: ({ children }) => (
                    <h2 className="sr-only">{children}</h2>
                  ),
                }}
              >
                {report}
              </Markdown>
            </Details>
          )}

          {/* The adversarial set, separate rather than mixed in: its numbers are
              over a different corpus and reading them as the demo's would be
              reading two systems as one. */}
          {adversarial && (
            <Details
              summary={t.evaluation.adversarial}
              note={t.evaluation.adversarialNote}
            >
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{ h1: ({ children }) => <h2>{children}</h2> }}
              >
                {adversarial}
              </Markdown>
            </Details>
          )}

          <p className="mt-12 border-t border-line pt-4 text-xs text-ink-faint">
            {t.evaluation.regenerate}:{" "}
            <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono">
              python -m eval.run_eval
            </code>
          </p>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
