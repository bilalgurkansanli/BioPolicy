"use client";

import { useLocale } from "@/components/LocaleProvider";
import type { Summary } from "@/lib/summary";
import type { Citation } from "@/lib/types";

/**
 * A summary turn: the schema, in the shape the question asked for.
 *
 * Styled as an assistant turn because that is what it is — an answer to
 * something the user typed. It carries a badge saying where it came from, and
 * that badge is not decoration: everything else in this column was written by a
 * model, this was assembled from rows that were extracted and bound earlier.
 * A reader who cannot tell those apart cannot judge either.
 *
 * There is no cost line, because there was no call. The absence of one where
 * every other card has one is the honest signal, and it is the same reasoning
 * the cached-answer label was given.
 */
export function SummaryCard({
  summary,
  onCite,
  activeCitation,
}: {
  summary: Summary;
  onCite: (citation: Citation, key: string) => void;
  activeCitation: string | null;
}) {
  const { t } = useLocale();
  const copy = t.workspace.summary;
  const fields = t.workspace.profile.fields;

  return (
    <article className="rounded-2xl rounded-tl-md border border-accent/15 bg-surface p-4 shadow-[0_12px_32px_-28px_var(--accent-glow)]">
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-ink">
          {copy.titles[summary.kind]}
        </h3>
        <span className="rounded-full border border-line bg-surface-sunken px-2 py-0.5 text-[11px] text-ink-faint">
          {copy.badge}
        </span>
      </header>

      <div className="mt-3 space-y-3">
        {summary.sections.map((section) => (
          <section key={section.field}>
            <h4 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              {fields[section.field]}
              <span className="ml-1.5 font-normal normal-case tracking-normal">
                {section.entries.length}
              </span>
            </h4>
            <ul className="mt-1.5 space-y-1">
              {section.entries.map((entry, index) => {
                const key = `summary:${summary.kind}:${section.field}:${index}`;
                return (
                  <li key={key}>
                    <Row
                      label={entry.label}
                      value={entry.value}
                      citation={entry.citation}
                      active={activeCitation === key}
                      onSelect={() => onCite(entry.citation, key)}
                    />
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>

      {/* The half of a summary a chatbot cannot write. Withheld by `summarise`
          unless the whole document was read, so its presence is a claim about
          the document rather than about how far the sweep got. */}
      {summary.absent.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <h4 className="text-xs font-medium uppercase tracking-wide text-refuse">
            {copy.absentTitle}
          </h4>
          <p className="mt-1 flex flex-wrap gap-1.5">
            {summary.absent.map((field) => (
              <span
                key={field}
                className="rounded-full border border-refuse/25 bg-refuse-soft px-2 py-0.5 text-[11px] text-refuse"
              >
                {fields[field]}
              </span>
            ))}
          </p>
        </div>
      )}

      <p className="mt-3 text-xs leading-5 text-ink-faint">{copy.note}</p>
    </article>
  );
}

function Row({
  label,
  value,
  citation,
  active,
  onSelect,
}: {
  label: string;
  value: string;
  citation: Citation;
  active: boolean;
  onSelect: () => void;
}) {
  const { t } = useLocale();
  const locatable = citation.bbox !== null;

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!locatable}
      className={`w-full rounded-lg border px-2.5 py-1.5 text-left transition-colors ${
        active
          ? "border-highlight-ring bg-accent-soft"
          : "border-line bg-surface-sunken hover:border-line-strong"
      } ${locatable ? "cursor-pointer" : "cursor-default"}`}
    >
      <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        {label && (
          <span className="text-xs font-medium text-ink-muted">{label}</span>
        )}
        <span className="text-sm text-ink">{value}</span>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-ink-faint">
          {t.workspace.page}
          {citation.page_end > citation.page
            ? `${citation.page}–${citation.page_end}`
            : citation.page}
        </span>
      </span>
      <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-ink-faint">
        “{citation.quote}”
      </span>
    </button>
  );
}
