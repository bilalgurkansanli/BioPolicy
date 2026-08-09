"use client";

import { useLocale } from "@/components/LocaleProvider";
import type { Answer, Citation } from "@/lib/types";

/**
 * One assistant turn.
 *
 * A refusal is styled as a distinct, deliberate outcome rather than as an error
 * or an empty state. Refusing correctly is the behaviour this project exists to
 * demonstrate; making it look like a failure would undercut the whole claim.
 */
export function AnswerCard({
  answer,
  onCite,
  activeCitation,
  children,
}: {
  answer: Answer;
  onCite: (citation: Citation) => void;
  activeCitation: string | null;
  /**
   * Rendered at the foot of every variant, including the refusals.
   *
   * A refusal is exactly when someone wants to know what was retrieved — "it
   * says it cannot find it, but is the clause in there?" — so the evidence
   * panel must not be reserved for the answers that worked.
   */
  children?: React.ReactNode;
}) {
  const { t } = useLocale();

  if (answer.suppressed) {
    return (
      <article className="rounded-2xl rounded-tl-md border border-danger/40 bg-danger-soft p-4">
        <h3 className="text-sm font-semibold text-danger">
          {t.workspace.suppressedTitle}
        </h3>
        <p className="mt-1.5 text-sm leading-6 text-ink-muted">
          {t.workspace.suppressedBody}
        </p>
        {answer.suppression_reason && (
          <p className="mt-2 font-mono text-xs text-ink-faint">
            {answer.suppression_reason}
          </p>
        )}
        <CostLine answer={answer} />
        {children}
      </article>
    );
  }

  if (answer.refused) {
    return (
      <article className="rounded-2xl rounded-tl-md border border-refuse/35 bg-refuse-soft p-4">
        <h3 className="text-sm font-semibold text-refuse">
          {t.workspace.refusedTitle}
        </h3>
        <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-ink">
          {answer.answer}
        </p>
        <CostLine answer={answer} />
        {children}
      </article>
    );
  }

  return (
    <article className="rounded-2xl rounded-tl-md border border-accent/15 bg-surface p-4 shadow-[0_12px_32px_-28px_var(--accent-glow)]">
      <p className="whitespace-pre-wrap text-[15px] leading-7 text-ink">
        {answer.answer}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-faint">
        <span>
          {t.workspace.confidence}:{" "}
          <span className="font-medium text-ink-muted">
            {t.workspace.confidenceValue[answer.confidence]}
          </span>
        </span>
        {answer.groundedness !== null && (
          <>
            <Dot />
            <span className="inline-flex items-center gap-1.5">
              {t.workspace.groundedness}
              <span className="font-mono tabular-nums text-ink-muted">
                {answer.groundedness.toFixed(2)}
              </span>
              <span className="h-1 w-10 overflow-hidden rounded-full bg-line">
                <span
                  className="block h-full bg-good"
                  style={{
                    width: `${Math.round(answer.groundedness * 100)}%`,
                  }}
                />
              </span>
            </span>
          </>
        )}
        {answer.verified !== null && (
          <>
            <Dot />
            <span className={answer.verified ? "text-good" : undefined}>
              {answer.verified
                ? t.workspace.verified
                : t.workspace.unverified}
            </span>
          </>
        )}
      </div>

      {answer.caveats.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <h4 className="text-xs font-medium text-ink-muted">
            {t.workspace.caveats}
          </h4>
          <ul className="mt-1.5 space-y-1">
            {answer.caveats.map((caveat) => (
              <li key={caveat} className="text-xs leading-5 text-ink-muted">
                {caveat}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 border-t border-line pt-3">
        <h4 className="text-xs font-medium text-ink-muted">
          {t.workspace.citations}
        </h4>
        {answer.citations.length === 0 ? (
          <p className="mt-1.5 text-xs text-ink-faint">
            {t.workspace.citationsNone}
          </p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {answer.citations.map((citation, index) => (
              <li key={`${citation.context_id}:${index}`}>
                <CitationChip
                  citation={citation}
                  onSelect={() => onCite(citation)}
                  active={
                    activeCitation === `${citation.context_id}:${index}`
                  }
                  id={`${citation.context_id}:${index}`}
                />
              </li>
            ))}
          </ul>
        )}
        {answer.dropped_citations > 0 && (
          <p className="mt-2 text-xs text-refuse">
            {answer.dropped_citations} {t.workspace.droppedCitations}
          </p>
        )}
      </div>

      <CostLine answer={answer} />
      {children}
    </article>
  );
}

function CitationChip({
  citation,
  onSelect,
  active,
}: {
  citation: Citation;
  onSelect: () => void;
  active: boolean;
  id: string;
}) {
  const { t } = useLocale();
  const locatable = citation.bbox !== null;

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!locatable}
      className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
        active
          ? "border-highlight-ring bg-accent-soft"
          : "border-line bg-surface-sunken hover:border-line-strong"
      } ${locatable ? "cursor-pointer" : "cursor-default"}`}
    >
      <span className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-faint">
        {/* A range when the chunk crosses a page break. The quote can be on
            either side of it, so naming only the first page would contradict
            the highlight the chip is about to put on the second. */}
        <span className="font-mono font-medium text-ink-muted">
          {t.workspace.page}
          {citation.page_end > citation.page
            ? `${citation.page}–${citation.page_end}`
            : citation.page}
        </span>
        {citation.section_path && (
          <>
            <Dot />
            <span className="truncate">{citation.section_path}</span>
          </>
        )}
        <Dot />
        <span
          title={citation.exact ? undefined : t.workspace.fuzzyTitle}
          className={citation.exact ? "text-good" : "text-refuse"}
        >
          {citation.exact ? t.workspace.exact : t.workspace.fuzzy}
        </span>
      </span>
      <span className="mt-1 block text-xs leading-5 text-ink">
        “{citation.quote}”
      </span>
    </button>
  );
}

function CostLine({ answer }: { answer: Answer }) {
  const { t } = useLocale();

  // A cached answer costs nothing and arrives in milliseconds. Printing
  // "$0.0000" beside it without explanation would read as a free system rather
  // than as a stored one — and this project publishes what a question costs.
  if (answer.cached !== null) {
    return (
      <p
        className="mt-3 font-mono text-[11px] text-ink-faint"
        title={t.workspace.cachedNote}
      >
        {t.workspace.cached.replace("{count}", String(answer.cached + 1))}
      </p>
    );
  }

  return (
    <p
      className="mt-3 font-mono text-[11px] text-ink-faint"
      title={t.workspace.costNote}
    >
      ${answer.cost_usd.toFixed(4)} {t.workspace.cost}
    </p>
  );
}

function Dot() {
  return (
    <span aria-hidden className="text-ink-faint/60">
      ·
    </span>
  );
}
