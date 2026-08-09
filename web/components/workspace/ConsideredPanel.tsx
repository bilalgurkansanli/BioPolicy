"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import type { Citation, ConsideredChunk } from "@/lib/types";

/**
 * What the answer was built from, and what it was not.
 *
 * Retrieval puts eight passages in front of the model and the answer typically
 * cites two. The other six are the most informative thing an interface can show
 * about a wrong answer, because they separate the two failures that look
 * identical from the outside:
 *
 *   * the clause was never retrieved  -> a retrieval problem
 *   * it was retrieved and not used   -> a generation problem
 *
 * Collapsed by default. This is evidence for someone who wants to check, not
 * something to make every answer look complicated.
 */
export function ConsideredPanel({
  considered,
  citations,
  onOpen,
}: {
  considered: ConsideredChunk[];
  citations: Citation[];
  /** Opens the passage in the viewer, the same way a citation does. */
  onOpen?: (chunk: ConsideredChunk) => void;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  if (considered.length === 0) return null;

  const cited = new Set(citations.map((citation) => citation.context_id));
  const unused = considered.filter((chunk) => !cited.has(chunk.context_id));

  // Nothing to report when every passage was used — which does happen, and
  // saying so would be noise rather than transparency.
  if (unused.length === 0) return null;

  return (
    <div className="mt-3 border-t border-line pt-2.5">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 text-left text-[11px] text-ink-faint transition-colors hover:text-ink-muted"
      >
        <Chevron open={open} />
        <span>
          {t.workspace.considered.toggle
            .replace("{used}", String(considered.length - unused.length))
            .replace("{total}", String(considered.length))}
        </span>
      </button>

      {open && (
        <div className="mt-2.5 space-y-2">
          <p className="text-[11px] leading-4 text-ink-faint">
            {t.workspace.considered.explainer}
          </p>
          <ul className="space-y-1.5">
            {unused.map((chunk) => (
              <li key={chunk.context_id}>
                <button
                  type="button"
                  onClick={() => onOpen?.(chunk)}
                  disabled={!onOpen}
                  className="w-full rounded-lg border border-line bg-surface-sunken px-2.5 py-2 text-left transition-colors enabled:hover:border-line-strong disabled:cursor-default"
                >
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-ink-faint">
                    <span className="font-mono">{chunk.context_id}</span>
                    <span>{pageLabel(chunk, t.workspace.considered.page)}</span>
                    {chunk.section_path && (
                      <span className="truncate">{chunk.section_path}</span>
                    )}
                  </span>
                  <span className="mt-1 block text-[11px] leading-4 text-ink-muted">
                    {chunk.snippet}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function pageLabel(chunk: ConsideredChunk, word: string): string {
  return chunk.page === chunk.page_end
    ? `${word} ${chunk.page}`
    : `${word} ${chunk.page}–${chunk.page_end}`;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 12 12"
      className={`h-2.5 w-2.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
      aria-hidden="true"
    >
      <path
        d="M4 2.5 8 6l-4 3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
