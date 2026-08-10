"use client";

import { useLocale } from "@/components/LocaleProvider";
import { Badge } from "@/components/workspace/Badge";
import type { DocumentSummary } from "@/lib/types";

export function DocumentList({
  documents,
  selectedId,
  onSelect,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (document: DocumentSummary) => void;
}) {
  const { t } = useLocale();

  return (
    <div className="space-y-2">
      {documents.map((document) => {
        const selected = document.id === selectedId;
        const scanned = document.source_type === "scanned";
        return (
          <button
            key={document.id}
            type="button"
            onClick={() => onSelect(document)}
            aria-pressed={selected}
            className={`w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${
              selected
                ? "border-accent bg-accent-soft"
                : "border-line bg-surface hover:border-line-strong"
            }`}
          >
            <span className="block truncate font-mono text-xs text-ink">
              {document.filename}
            </span>
            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-faint">
              {document.detected_lang === "tr" || document.detected_lang === "en" ? (
                <Badge>{t.workspace.lang[document.detected_lang]}</Badge>
              ) : null}
              <Badge tone={scanned ? "warn" : "plain"}>
                {scanned
                  ? t.workspace.sourceType.scanned
                  : t.workspace.sourceType.native}
              </Badge>
              {document.page_count !== null && (
                <span>
                  {document.page_count} {t.workspace.pages}
                </span>
              )}
              {/* Only when something was found. A "clean" badge on every other
                  document would turn a narrow check into a broad assurance. */}
              {(document.injection_findings?.length ?? 0) > 0 && (
                <Badge tone="warn">{t.workspace.injection.badge}</Badge>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

