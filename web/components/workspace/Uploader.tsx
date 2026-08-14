"use client";

import { useCallback, useRef, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { ApiError, uploadDocument } from "@/lib/api";
import { NotSignedInError } from "@/lib/supabase";

export type UploadFailure = {
  title: string;
  message: string;
};

/**
 * Drop a PDF, or pick one.
 *
 * The file goes straight to object storage against a signed URL — it never
 * passes through the API (constraint C1). What this component owns is the part
 * the visitor sees: real upload progress (XHR, because fetch still cannot
 * report it), and a refusal that says which limit was hit rather than "failed".
 */
export function Uploader({
  maxBytes,
  retentionHours,
  disabled,
  onUploaded,
  onFailure,
  compact = false,
  disabledNote,
}: {
  maxBytes: number;
  retentionHours: number;
  disabled: boolean;
  onUploaded: (documentId: string, filename: string) => void;
  onFailure: (failure: UploadFailure | null) => void;
  /**
   * One line instead of a panel, for the visitor who has already uploaded
   * something. The invitation has been accepted; what is left is a way to add
   * another, and the space it gives back goes to the list of what is there.
   */
  compact?: boolean;
  /**
   * Why this is disabled, when the reason is the visitor's own allowance.
   *
   * `disabled` collapses three different situations — no credentials, no
   * session, no uploads left today — and only the last one is the visitor's to
   * understand. Given a note, the control says it instead of leaving a
   * not-allowed cursor to be the entire explanation.
   */
  disabledNote?: string;
}) {
  const { t } = useLocale();
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);

  const megabytes = Math.round(maxBytes / (1024 * 1024));
  const limits = t.upload.limits
    .replace("{mb}", String(megabytes))
    .replace("{hours}", String(retentionHours));

  const send = useCallback(
    async (file: File) => {
      onFailure(null);

      // Checked here as well as on the server. A visitor who picked a 200MB
      // file should be told immediately rather than after uploading it.
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        onFailure({ title: t.upload.failedTitle, message: t.upload.notPdf });
        return;
      }
      if (file.size > maxBytes) {
        onFailure({
          title: t.upload.failedTitle,
          message: `${t.upload.tooLarge} ${t.upload.limits
            .replace("{mb}", String(megabytes))
            .replace("{hours}", String(retentionHours))}`,
        });
        return;
      }

      setProgress(0);
      try {
        onUploaded(await uploadDocument(file, setProgress), file.name);
      } catch (error) {
        if (error instanceof NotSignedInError) {
          onFailure({
            title: t.account.signInTitle,
            message: t.account.signInBody,
          });
        } else if (error instanceof ApiError) {
          onFailure(
            error.isQuota
              ? { title: t.upload.quotaTitle, message: t.upload.quotaDocuments }
              : error.isBudget
                ? { title: t.upload.budgetTitle, message: t.upload.budgetBody }
                : error.isBlocked
                  ? { title: t.upload.blockedTitle, message: t.upload.blockedBody }
                  : // Nothing recognised the code, so the API's own sentence is
                    // the only thing left that describes what happened.
                    { title: t.upload.failedTitle, message: error.message },
          );
        } else {
          onFailure({ title: t.upload.failedTitle, message: t.workspace.errorBody });
        }
      } finally {
        setProgress(null);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [maxBytes, megabytes, onFailure, onUploaded, retentionHours, t],
  );

  const busy = progress !== null;

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled && !busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file && !disabled && !busy) void send(file);
        }}
        className={`rounded-xl border border-dashed text-center transition-colors ${
          compact ? "px-3 py-2" : "px-3 py-4"
        } ${
          dragging
            ? "border-accent bg-accent-soft"
            : "border-line-strong bg-surface"
        } ${disabled && !disabledNote ? "opacity-50" : ""}`}
      >
        {disabledNote && !busy ? (
          <p className="text-xs leading-5 text-ink-faint">{disabledNote}</p>
        ) : busy ? (
          <div>
            <p className="text-xs text-ink-muted">
              {t.upload.uploading} {Math.round((progress ?? 0) * 100)}%
            </p>
            <div
              role="progressbar"
              aria-valuenow={Math.round((progress ?? 0) * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="mt-2 h-1 w-full overflow-hidden rounded-full bg-line"
            >
              <div
                className="h-full bg-accent transition-[width] duration-150"
                style={{ width: `${Math.round((progress ?? 0) * 100)}%` }}
              />
            </div>
          </div>
        ) : (
          <>
            {compact ? (
              <button
                type="button"
                disabled={disabled}
                onClick={() => inputRef.current?.click()}
                title={limits}
                className="w-full text-xs font-medium text-ink-muted transition-colors hover:text-accent disabled:cursor-not-allowed"
              >
                + {t.upload.choose}
              </button>
            ) : (
              <>
                <p className="text-xs text-ink-muted">{t.upload.drop}</p>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => inputRef.current?.click()}
                  className="mt-2 rounded-lg border border-line-strong px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:bg-surface-sunken disabled:cursor-not-allowed"
                >
                  {t.upload.choose}
                </button>
              </>
            )}
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void send(file);
          }}
        />
      </div>
      {/* Read once, on the way in. Beside a list of documents it is a line of
          small print between the visitor and what they came back for. */}
      {!compact && (
        <p className="mt-2 text-[11px] leading-4 text-ink-faint">{limits}</p>
      )}
    </div>
  );
}
