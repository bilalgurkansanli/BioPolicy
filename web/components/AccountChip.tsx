"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";
import { GoogleMark } from "@/components/workspace/SignInGate";

/**
 * The account, in the header: who you are and what is left today.
 *
 * The remaining count is here rather than only above the composer because it is
 * the thing that decides whether the next click will work, and somebody who has
 * run out should be able to see why without opening a document first.
 */
export function AccountChip() {
  const { t } = useLocale();
  const { ready, signedIn, me, signIn, signOut, configured } = useSession();
  const [failed, setFailed] = useState(false);

  if (!configured || !ready) return null;

  if (!signedIn) {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void signIn().catch(() => setFailed(true))}
          className="inline-flex h-9 items-center gap-2 rounded-full border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink transition-colors hover:bg-surface-sunken"
        >
          <GoogleMark />
          <span className="hidden sm:inline">{t.account.signIn}</span>
        </button>
        {/* The gate below the composer carries the full explanation; up here
            there is only room to say it did not work. */}
        {failed && (
          <span className="hidden text-[11px] text-danger sm:inline">
            {t.account.providerDisabledTitle}
          </span>
        )}
      </div>
    );
  }

  const left = me?.allowance.questions_left ?? null;

  return (
    <div className="flex items-center gap-2">
      <span className="hidden max-w-[16ch] truncate text-xs text-ink-muted sm:inline">
        {me?.email}
      </span>
      <span
        className={`rounded-full border px-2 py-0.5 font-mono text-[11px] ${
          left === 0
            ? "border-refuse/40 bg-refuse-soft text-refuse"
            : "border-line text-ink-muted"
        }`}
        title={t.account.remaining}
      >
        {/* Unlimited is `null`, and must not render as a zero. */}
        {left === null ? t.account.unlimited : `${left} ${t.account.questions}`}
      </span>
      <button
        type="button"
        onClick={() => void signOut()}
        className="rounded-md px-2 py-1 text-xs text-ink-faint transition-colors hover:text-ink"
      >
        {t.account.signOut}
      </button>
    </div>
  );
}
