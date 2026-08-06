"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useLocale } from "@/components/LocaleProvider";
import { MetricHistory, type HistoryRow } from "@/components/MetricHistory";
import { SpendCounter } from "@/components/SpendCounter";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

/** One report, as written by the tool, in each language it writes it in. */
type Rendered = { en: string | null; tr: string | null };

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

          {report === null ? (
            <p className="mt-10 rounded-xl border border-line bg-surface p-4 text-sm text-ink-muted">
              {t.evaluation.missing}
            </p>
          ) : (
            <div className="report mt-10 overflow-x-auto">
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
            </div>
          )}

          <SpendCounter />
          <MetricHistory rows={history} />

          {/* The adversarial set, after the main report rather than mixed into
              it: its numbers are over a different corpus and reading them as
              the demo's would be reading two systems as one. */}
          {adversarial && (
            <div className="report mt-10 overflow-x-auto border-t border-line pt-8">
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{ h1: ({ children }) => <h2>{children}</h2> }}
              >
                {adversarial}
              </Markdown>
            </div>
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
