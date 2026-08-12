"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { HeadlineMetrics } from "@/components/HeadlineMetrics";
import { useLocale } from "@/components/LocaleProvider";
import { MetricHistory, type HistoryRow } from "@/components/MetricHistory";
import { SpendCounter } from "@/components/SpendCounter";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { splitSections } from "@/lib/report-sections";
import { REPO_URL } from "@/lib/site";

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
  children,
}: {
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group border-b border-line last:border-b-0">
      <summary className="flex cursor-pointer list-none items-baseline gap-2 py-3 text-sm text-ink-muted transition-colors marker:content-none hover:text-ink">
        <span
          aria-hidden
          className="font-mono text-xs text-ink-faint transition-transform group-open:rotate-90"
        >
          ›
        </span>
        {summary}
      </summary>
      <div className="report overflow-x-auto pb-6 pl-5">{children}</div>
    </details>
  );
}

/**
 * One generated report, as a list of its own sections.
 *
 * Each section is its own disclosure, so the page offers a menu of names
 * instead of one control that unfolds a document. The heading is dropped from
 * the body because it is already the label on the row that opened it.
 */
function ReportSections({ markdown }: { markdown: string }) {
  return (
    <div className="mt-4 border-t border-line">
      {splitSections(markdown).map((section) => (
        <Details key={section.heading} summary={section.heading}>
          <Markdown remarkPlugins={[remarkGfm]}>{section.body}</Markdown>
        </Details>
      ))}
    </div>
  );
}

/**
 * The adversarial run as three numbers and a link, rather than as a second copy
 * of the report above it.
 *
 * Both runs are rendered by the same generator, so listing this one's sections
 * put the same seven names on the page twice — and a reader who had just
 * scrolled past "Önce bunu okuyun / Koşu / Ablasyon / …" could not tell the
 * second list from the first. The result is one number here, the corpus is one
 * sentence, and the rest of it is a file away.
 */
function adversarialRun(rows: HistoryRow[]): HistoryRow | undefined {
  // The shipped arm on the adversarial set, for the same reason the headline
  // numbers use it: the latest row is whichever experiment ran last.
  return [...rows]
    .reverse()
    .find((row) => row.set === "hard" && row.arm === "strict_guarded");
}

function AdversarialSummary({ run }: { run: HistoryRow }) {
  const { t, locale } = useLocale();

  const percent = (value: number) =>
    new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-GB", {
      style: "percent",
      maximumFractionDigits: 0,
    }).format(value);

  const file = locale === "tr" ? "report_hard.tr.md" : "report_hard.md";

  return (
    <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-3 border-t border-line pt-4">
      {[
        { value: percent(run.refusal_accuracy), label: t.evaluation.cards.refusalAccuracy },
        { value: percent(run.false_refusal_rate), label: t.evaluation.cards.falseRefusal },
        {
          value: String(run.questions),
          label: t.evaluation.adversarialQuestions,
        },
      ].map((stat) => (
        <div key={stat.label}>
          <p className="font-mono text-xl tabular-nums text-ink">{stat.value}</p>
          <p className="mt-0.5 text-xs text-ink-faint">{stat.label}</p>
        </div>
      ))}
      <a
        href={`${REPO_URL}/blob/main/eval/${file}`}
        target="_blank"
        rel="noopener noreferrer"
        className="ml-auto text-xs text-accent underline-offset-4 hover:underline"
      >
        {t.evaluation.adversarialFile}
      </a>
    </div>
  );
}

/** The name of a report, and what is inside it, above its list of sections. */
function Group({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <h2 className="text-sm font-medium text-ink">{title}</h2>
      <p className="mt-1.5 text-xs leading-5 text-ink-faint">{note}</p>
      {children}
    </section>
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
  // The file has to exist and the run has to be in the history: the group shows
  // numbers from the second and links to the first, so either one missing
  // leaves a heading with nothing under it.
  const adversarial = pick(hard) && adversarialRun(history);

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
            <Group
              title={t.evaluation.fullReport}
              note={t.evaluation.fullReportNote}
            >
              <ReportSections markdown={report} />
            </Group>
          )}

          {/* The adversarial set, separate rather than mixed in: its numbers are
              over a different corpus and reading them as the demo's would be
              reading two systems as one. */}
          {adversarial && (
            <Group
              title={t.evaluation.adversarial}
              note={t.evaluation.adversarialNote}
            >
              <AdversarialSummary run={adversarial} />
            </Group>
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
