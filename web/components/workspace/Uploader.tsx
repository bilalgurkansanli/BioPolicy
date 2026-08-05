"use client";

import { useCallback, useRef, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { ApiError, uploadDocument } from "@/lib/api";
import { AuthUnavailableError } from "@/lib/supabase";

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
}: {
  maxBytes: number;
  retentionHours: number;
  disabled: boolean;
  onUploaded: (documentId: string, filename: string) => void;
  onFailure: (failure: UploadFailure | null) => void;
}) {
  const { t } = useLocale();
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);

  const megabytes = Math.round(maxBytes / (1024 * 1024));

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
        if (error instanceof AuthUnavailableError) {
          onFailure({
            title: t.upload.authDisabledTitle,
            message: error.anonymousDisabled
              ? t.upload.authDisabled
              : t.upload.signInFailed,
          });
        } else if (error instanceof ApiError) {
          onFailure({
            title: error.isQuota
              ? t.upload.quotaTitle
              : error.isBudget
                ? t.upload.budgetTitle
                : t.upload.failedTitle,
            // The API's own message: it names the limit and when it resets, and
            // is already written for a person to read.
            message: error.message,
          });
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
        className={`rounded-lg border border-dashed px-3 py-4 text-center transition-colors ${
          dragging
            ? "border-accent bg-accent-soft"
            : "border-line-strong bg-surface"
        } ${disabled ? "opacity-50" : ""}`}
      >
        {busy ? (
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
            <p className="text-xs text-ink-muted">{t.upload.drop}</p>
            <button
              type="button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              className="mt-2 rounded-md border border-line-strong px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:bg-surface-sunken disabled:cursor-not-allowed"
            >
              {t.upload.choose}
            </button>
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
      <p className="mt-2 text-[11px] leading-4 text-ink-faint">
        {t.upload.limits
          .replace("{mb}", String(megabytes))
          .replace("{hours}", String(retentionHours))}
      </p>
    </div>
  );
}
