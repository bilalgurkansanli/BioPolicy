"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import type { DocumentStatus, DocumentSummary } from "@/lib/types";

/**
 * The visitor's own uploads.
 *
 * Different from the sample list in one way that matters: these are still being
 * worked on. Ingestion is asynchronous (ADR 007), so a document arrives here
 * `queued` and walks through parsing, OCR, chunking and embedding before it can
 * be asked anything. The stage names come from the API rather than being
 * duplicated here, so the label always matches what the pipeline is doing.
 */
export function MyDocumentList({
  documents,
  progress,
  selectedId,
  onSelect,
  onDelete,
}: {
  documents: DocumentSummary[];
  progress: Record<string, DocumentStatus>;
  selectedId: string | null;
  onSelect: (document: DocumentSummary) => void;
  onDelete: (documentId: string) => void;
}) {
  const { t } = useLocale();
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <ul className="space-y-2">
      {documents.map((document) => {
        const status = progress[document.id];
        const state = status?.status ?? document.status;
        const ready = state === "ready";
        const failed = state === "failed";
        const selected = document.id === selectedId;

        return (
          <li
            key={document.id}
            className={`rounded-xl border px-3 py-2.5 transition-colors ${
              selected ? "border-accent bg-accent-soft" : "border-line bg-surface"
            }`}
          >
            <div className="flex items-start gap-2">
              <button
                type="button"
                disabled={!ready}
                onClick={() => onSelect(document)}
                aria-pressed={selected}
                className={`min-w-0 flex-1 text-left ${
                  ready ? "cursor-pointer" : "cursor-default"
                }`}
              >
                <span className="block truncate font-mono text-xs text-ink">
                  {document.filename}
                </span>
              </button>

              {confirming === document.id ? null : (
                <button
                  type="button"
                  onClick={() => setConfirming(document.id)}
                  aria-label={t.upload.remove}
                  title={t.upload.remove}
                  className="shrink-0 rounded p-0.5 text-ink-faint transition-colors hover:text-danger"
                >
                  <svg
                    aria-hidden
                    viewBox="0 0 16 16"
                    className="size-3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                  >
                    <path d="M3 4h10M6.5 4V2.8h3V4M5 4l.6 9h4.8L11 4" />
                  </svg>
                </button>
              )}
            </div>

            {confirming === document.id ? (
              // Deletion is immediate and irreversible — the file leaves the
              // bucket, not a recycle bin — so it asks first.
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[11px] text-ink-muted">
                  {t.upload.confirmRemove}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setConfirming(null);
                    onDelete(document.id);
                  }}
                  className="rounded border border-danger/50 px-1.5 py-0.5 text-[11px] text-danger"
                >
                  {t.upload.confirmYes}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(null)}
                  className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-muted"
                >
                  {t.upload.confirmNo}
                </button>
              </div>
            ) : (
              <>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-faint">
                  <span className={failed ? "text-danger" : undefined}>
                    {t.upload.stages[
                      state as keyof typeof t.upload.stages
                    ] ?? state}
                  </span>
                  {ready && document.page_count !== null && (
                    <span>
                      {document.page_count} {t.workspace.pages}
                    </span>
                  )}
                  {ready &&
                    (document.detected_lang === "tr" ||
                      document.detected_lang === "en") && (
                      <span>{t.workspace.lang[document.detected_lang]}</span>
                    )}
                </div>

                {!ready && !failed && status && (
                  <div className="mt-1.5 h-0.5 w-full overflow-hidden rounded-full bg-line">
                    <div
                      className="h-full bg-accent transition-[width] duration-500"
                      style={{
                        width: `${Math.round(
                          ((status.stage_index + 1) / status.stage_count) * 100,
                        )}%`,
                      }}
                    />
                  </div>
                )}

                {failed && status?.error && (
                  <p className="mt-1 text-[11px] leading-4 text-danger">
                    {status.error}
                  </p>
                )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
