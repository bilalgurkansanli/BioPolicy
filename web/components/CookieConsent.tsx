"use client";

import Script from "next/script";
import Link from "next/link";
import { useSyncExternalStore } from "react";

import { useLocale } from "@/components/LocaleProvider";
import {
  getConsentSnapshot,
  getServerConsentSnapshot,
  setConsent,
  subscribeToConsent,
} from "@/lib/consent-store";

// Interpolated into a script the browser executes, so it is checked rather than
// trusted: a project id is alphanumeric, and anything else is a misconfigured
// deployment, not a tag.
const RAW_CLARITY_ID = process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID ?? "";
const CLARITY_ID = /^[a-z0-9]+$/i.test(RAW_CLARITY_ID) ? RAW_CLARITY_ID : "";

/**
 * The cookie decision, and the one thing it turns on.
 *
 * The tag is not loaded and then switched off; it is not loaded at all until
 * somebody says yes. A tracker that runs while the banner is still on screen
 * has already done the thing the banner is asking about.
 *
 * Signing in counts as saying yes — the sign-in screen says so, above the
 * button — which is why a visitor who has been there never sees this banner.
 */
export function CookieConsent() {
  const { t } = useLocale();
  const consent = useSyncExternalStore(
    subscribeToConsent,
    getConsentSnapshot,
    getServerConsentSnapshot,
  );

  return (
    <>
      {consent === "granted" && CLARITY_ID && (
        // Not a plain `src`. The file at `clarity.ms/tag/{id}` is the second
        // half of the tag: its first statement is `window.clarity("metadata",
        // …)`, so it throws unless the queue shim below has already defined
        // that function. Loading it directly downloads a script that fails on
        // its own first line — which looks exactly like a tag that works.
        //
        // The id is also deliberately not `clarity`: an element's id becomes a
        // global of the same name, and the shim only installs itself when
        // `window.clarity` is falsy.
        <Script id="ms-clarity" strategy="afterInteractive">
          {`(function(c,l,a,r,i,t,y){
              c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
              t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
              y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
            })(window, document, "clarity", "script", ${JSON.stringify(CLARITY_ID)});`}
        </Script>
      )}

      {consent === "unset" && (
        <div className="fixed inset-x-0 bottom-0 z-50 px-4 pb-4 sm:px-6 sm:pb-6">
          <div className="menu-pop mx-auto flex w-full max-w-3xl flex-col gap-3 rounded-2xl border border-line bg-surface/95 p-4 shadow-[0_28px_60px_-28px_rgb(15_23_42_/_0.5)] backdrop-blur sm:flex-row sm:items-center sm:gap-4 sm:p-5">
            <p className="flex-1 text-xs leading-5 text-ink-muted">
              {t.cookies.bannerBody}{" "}
              <Link
                href="/signin"
                className="font-medium text-accent underline-offset-2 hover:underline"
              >
                {t.cookies.bannerLink}
              </Link>
            </p>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => setConsent("denied")}
                className="h-9 flex-1 rounded-full border border-line-strong px-4 text-xs font-medium text-ink transition-colors hover:bg-surface-sunken sm:flex-none"
              >
                {t.cookies.decline}
              </button>
              <button
                type="button"
                onClick={() => setConsent("granted")}
                className="cta-gradient cta-sheen h-9 flex-1 rounded-full px-4 text-xs font-semibold text-on-accent shadow-[0_6px_18px_-8px_var(--accent-glow)] sm:flex-none"
              >
                <span>{t.cookies.accept}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
