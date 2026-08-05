"use client";

import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";
import { AuthUnavailableError } from "@/lib/supabase";

/**
 * What stands where the composer would be, for a visitor who is not signed in.
 *
 * Placed inside the conversation rather than in front of the whole workspace on
 * purpose: the samples and the viewer stay readable without an account, so
 * somebody can see what the thing does before being asked for anything. The
 * gate appears at the point where it becomes true — asking costs money, and the
 * daily limit has to be counted against somebody.
 */
export function SignInGate() {
  const { t } = useLocale();
  const { signIn, configured } = useSession();
  const [failure, setFailure] = useState<{ title: string; body: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setFailure(null);
    setBusy(true);
    try {
      await signIn();
      // The browser leaves for Google here; `busy` stays true until it does.
    } catch (error) {
      setBusy(false);
      if (error instanceof AuthUnavailableError && error.providerDisabled) {
        setFailure({
          title: t.account.providerDisabledTitle,
          body: t.account.providerDisabled,
        });
      } else {
        setFailure({
          title: t.account.providerDisabledTitle,
          body: t.account.signInFailed,
        });
      }
    }
  };

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">{t.account.signInTitle}</h3>
      <p className="mt-1.5 text-sm leading-6 text-ink-muted">
        {t.account.signInBody}
      </p>

      <button
        type="button"
        onClick={() => void start()}
        disabled={busy || !configured}
        className="mt-4 inline-flex h-10 items-center gap-2.5 rounded-lg border border-line-strong bg-surface px-4 text-sm font-medium text-ink transition-colors hover:bg-surface-sunken disabled:opacity-50"
      >
        <GoogleMark />
        {t.account.signIn}
      </button>

      <p className="mt-3 text-xs leading-5 text-ink-faint">
        {t.account.signInWhy}
      </p>

      {failure && (
        <div className="mt-3 rounded-lg border border-danger/40 bg-danger-soft p-2.5">
          <p className="text-xs font-medium text-danger">{failure.title}</p>
          <p className="mt-1 text-[11px] leading-4 text-ink-muted">
            {failure.body}
          </p>
        </div>
      )}
    </div>
  );
}

/** Google's mark, drawn rather than fetched: the CSP allows no remote images. */
export function GoogleMark() {
  return (
    <svg aria-hidden viewBox="0 0 18 18" className="size-4">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}
