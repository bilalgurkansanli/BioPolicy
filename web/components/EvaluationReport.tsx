"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useLocale } from "@/components/LocaleProvider";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

/**
 * The report itself stays in English regardless of interface language: it is a
 * verbatim rendering of a file in the repository, and translating it here would
 * mean the page no longer showed what the tool actually wrote.
 */
export function EvaluationReport({ markdown }: { markdown: string | null }) {
  const { t } = useLocale();

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

          {markdown === null ? (
            <p className="mt-10 rounded-lg border border-line bg-surface p-4 text-sm text-ink-muted">
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
                {markdown}
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
