"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { GoogleMark } from "@/components/workspace/SignInGate";
import { AuthUnavailableError } from "@/lib/supabase";

/** Where the two documents are read, without leaving the page they are on. */
type Sheet = "privacy" | "terms";

/**
 * Confirmation that signing out worked, for the visitor who was sent here by
 * it. Signing out is silent otherwise: the page simply changes, which reads as
 * having been thrown out rather than having left.
 */
function SignedOutNote({ label }: { label: string }) {
  const params = useSearchParams();
  if (params.get("signed-out") === null) return null;

  return (
    <p className="mx-auto mb-4 w-fit rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs text-ink-muted">
      {label}
    </p>
  );
}

/**
 * The sign-in screen, and where signing out lands.
 *
 * The terms are on this page rather than behind links to two more pages,
 * because the moment someone is asked to accept something is the moment they
 * should be able to read it — a policy one navigation away is a policy nobody
 * opens.
 */
export default function SignInPage() {
  const { t } = useLocale();
  const { ready, signedIn, signIn, configured } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ title: string; body: string } | null>(
    null,
  );
  const [sheet, setSheet] = useState<Sheet | null>(null);

  // Somebody who is already signed in has nothing to do here.
  useEffect(() => {
    if (ready && signedIn) router.replace("/app");
  }, [ready, signedIn, router]);

  const start = async () => {
    setFailure(null);
    setBusy(true);
    try {
      // Into the workspace, not back here: this page is a door, and coming back
      // to a door you have already walked through is not an arrival.
      await signIn("/app");
      // The browser leaves for Google here; `busy` stays true until it does.
    } catch (error) {
      setBusy(false);
      setFailure({
        title: t.account.providerDisabledTitle,
        body:
          error instanceof AuthUnavailableError && error.providerDisabled
            ? t.account.providerDisabled
            : t.account.signInFailed,
      });
    }
  };

  const documents = [
    { key: "privacy" as const, title: t.signin.privacyTitle, points: t.signin.privacy },
    { key: "terms" as const, title: t.signin.termsTitle, points: t.signin.terms },
  ];

  return (
    <>
      <SiteHeader />

      <main className="relative isolate flex-1 overflow-hidden">
        <div
          aria-hidden
          className="hero-wash pointer-events-none absolute inset-0 -z-10"
        />
        <div
          aria-hidden
          className="hero-grid pointer-events-none absolute inset-0 -z-10 opacity-70"
        />

        <div className="mx-auto w-full max-w-lg px-4 pb-20 pt-14 sm:px-6 sm:pt-20">
          {/* Reading the query is what makes this page prerenderable only up to
              the boundary; without it the whole route would have to be. */}
          <Suspense fallback={null}>
            <SignedOutNote label={t.signin.signedOut} />
          </Suspense>

          <div className="rounded-3xl border border-line bg-surface/90 p-7 text-center shadow-[0_30px_70px_-40px_rgb(15_23_42_/_0.45)] backdrop-blur sm:p-9">
            <Image
              src="/logo.png"
              alt=""
              width={206}
              height={256}
              priority
              className="mx-auto h-14 w-auto"
            />
            <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
              {t.signin.title}
            </h1>
            <p className="mx-auto mt-3 max-w-sm text-pretty text-sm leading-6 text-ink-muted">
              {t.signin.lede}
            </p>

            <button
              type="button"
              onClick={() => void start()}
              disabled={busy || !configured}
              className="mt-7 inline-flex h-12 w-full items-center justify-center gap-3 rounded-full border border-line-strong bg-surface text-[15px] font-medium text-ink transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[0_14px_30px_-18px_var(--accent-glow)] disabled:translate-y-0 disabled:opacity-50 disabled:shadow-none"
            >
              <GoogleMark />
              {t.account.signIn}
            </button>

            {failure && (
              <div className="mt-4 rounded-2xl border border-danger/40 bg-danger-soft p-3 text-left">
                <p className="text-sm font-medium text-danger">{failure.title}</p>
                <p className="mt-1 text-xs leading-5 text-ink-muted">
                  {failure.body}
                </p>
              </div>
            )}

            <p className="mt-5 rounded-2xl bg-accent-soft px-4 py-3 text-left text-xs leading-5 text-ink-muted">
              {t.signin.why}
            </p>

            <Link
              href="/app"
              className="mt-5 inline-block text-sm font-medium text-accent underline-offset-4 hover:underline"
            >
              {t.signin.browse}
            </Link>
          </div>

          <p className="mt-8 text-center text-xs text-ink-faint">
            {t.signin.legalNote}
          </p>

          {/* One open at a time: two sheets side by side would turn a short
              page into a wall of text, which is how a policy stops being read. */}
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {documents.map((document) => (
              <button
                key={document.key}
                type="button"
                onClick={() =>
                  setSheet((open) => (open === document.key ? null : document.key))
                }
                aria-expanded={sheet === document.key}
                className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm transition-colors ${
                  sheet === document.key
                    ? "border-accent/40 bg-accent-soft text-accent"
                    : "border-line bg-surface text-ink-muted hover:border-line-strong hover:text-ink"
                }`}
              >
                {document.title}
                <svg
                  aria-hidden
                  viewBox="0 0 16 16"
                  fill="none"
                  className={`size-3 transition-transform duration-200 ${
                    sheet === document.key ? "rotate-180" : ""
                  }`}
                >
                  <path
                    d="m4 6 4 4 4-4"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            ))}
          </div>

          {documents.map((document) =>
            sheet === document.key ? (
              <article
                key={document.key}
                className="menu-pop mt-4 rounded-3xl border border-line bg-surface p-6 text-left"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="text-base font-semibold text-ink">
                    {document.title}
                  </h2>
                  <span className="shrink-0 text-[11px] text-ink-faint">
                    {t.signin.updated}
                  </span>
                </div>
                <dl className="mt-4 space-y-4">
                  {document.points.map((point) => (
                    <div key={point.title}>
                      <dt className="text-sm font-medium text-ink">
                        {point.title}
                      </dt>
                      <dd className="mt-1 text-sm leading-6 text-ink-muted">
                        {point.body}
                      </dd>
                    </div>
                  ))}
                </dl>
              </article>
            ) : null,
          )}
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
