"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";

import { AccountMenu } from "@/components/AccountMenu";
import { useLocale } from "@/components/LocaleProvider";
import { SlideLink } from "@/components/SlideLink";
import { LOCALES } from "@/lib/i18n";

const REPO_URL = "https://github.com/bilalgurkansanli/BioPolicy";

/**
 * The workspace is the point of the site, so it does not sit in a row of links:
 * it is a filled button on the right, with a slow halo behind it. Everything
 * else in the header is deliberately quieter.
 */
export function SiteHeader() {
  const { locale, setLocale, t } = useLocale();
  const pathname = usePathname();

  const onWorkspace = pathname === "/app";

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center gap-3 px-4 sm:gap-5 sm:px-6">
        {/* The way out of the workspace, and the only one: the slide runs
            backwards here so leaving retraces the step that got you in. */}
        <SlideLink href="/" direction="back" className="flex items-center gap-2.5">
          {/* Sized from its height: the shield is taller than it is wide, and
              pinning the width instead would leave it short of the wordmark. */}
          <Image
            src="/logo.png"
            alt=""
            width={206}
            height={256}
            priority
            className="h-8 w-auto"
          />
          {/* The wordmark folds away on a phone: the mark still identifies the
              site, and the room it frees is what keeps the call-to-action from
              being pushed off the row. */}
          <span className="hidden text-[15px] font-semibold tracking-tight text-ink sm:inline">
            Bio<span className="text-accent">Policy</span>
          </span>
        </SlideLink>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <AccountMenu />

          {/* The measurements, back in the header — quietly, and only where
              there is room for them. On a phone the row is already full and
              this is the one item the footer also carries. */}
          {/* The direction is read from where the click came from, not fixed
              on the link. The site has one left-to-right axis — the landing
              page, then the workspace — and the report sits off to the side of
              it. Arriving from the landing page is a step further in, so the
              page advances; arriving from the workspace is a step back out, so
              it retreats. A single hard-coded direction would be right in one
              of those cases and backwards in the other, which reads as the
              interface having lost its place. */}
          <SlideLink
            href="/eval"
            direction={pathname === "/app" ? "back" : "forward"}
            aria-current={pathname === "/eval" ? "page" : undefined}
            className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1.5 text-sm transition-colors hover:text-ink sm:inline-flex ${
              pathname === "/eval" ? "text-ink" : "text-ink-muted"
            }`}
          >
            <MetricsMark />
            {t.evaluation.title}
          </SlideLink>

          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t.nav.source}
            className="inline-flex items-center gap-1.5 rounded-full px-2 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink sm:px-2.5"
          >
            <GitHubMark />
            <span className="hidden sm:inline">{t.nav.source}</span>
          </a>

          <LocaleSwitch locale={locale} setLocale={setLocale} label={t.language.label} />

          {/* In the workspace the button has nowhere left to send anyone: an
              invitation to the page you are already on is a label, not a
              control. It turns around and offers the way out instead — quietly,
              because leaving is not the thing this header is for. */}
          {onWorkspace ? (
            <SlideLink
              href="/"
              direction="back"
              className="group inline-flex h-9 items-center gap-1.5 rounded-full border border-line-strong bg-surface pl-3 pr-4 text-sm font-medium text-ink-muted transition-colors hover:border-accent/40 hover:text-ink"
            >
              <svg
                aria-hidden
                viewBox="0 0 16 16"
                fill="none"
                className="size-3.5 transition-transform duration-200 group-hover:-translate-x-0.5"
              >
                <path
                  d="M13 8H3m0 0 4-4M3 8l4 4"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="hidden sm:inline">{t.nav.backHome}</span>
              <span className="sm:hidden">{t.nav.home}</span>
            </SlideLink>
          ) : (
            <div className="relative">
              {/* The halo is its own element rather than a pseudo-element so it
                  can paint over the translucent header background instead of
                  under it. */}
              <span
                aria-hidden
                className="cta-halo absolute -inset-1 rounded-full opacity-50"
              />
              <SlideLink
                href="/app"
                direction="forward"
                className="cta-gradient cta-sheen group relative inline-flex h-9 items-center gap-1.5 rounded-full pl-4 pr-3.5 text-sm font-semibold text-on-accent shadow-[0_6px_18px_-8px_var(--accent-glow)] hover:-translate-y-px hover:shadow-[0_12px_26px_-10px_var(--accent-glow)]"
              >
                <span>{t.nav.workspace}</span>
                <svg
                  aria-hidden
                  viewBox="0 0 16 16"
                  fill="none"
                  className="size-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
                >
                  <path
                    d="M3 8h10m0 0-4-4m4 4-4 4"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </SlideLink>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

/**
 * A segmented control rather than two buttons: the selected language is a pill
 * that slides between the two halves, so switching reads as one control
 * changing state instead of two controls swapping colour.
 *
 * The indicator is positioned from the locale index, which keeps it correct if
 * a third language is ever added.
 */
function LocaleSwitch({
  locale,
  setLocale,
  label,
}: {
  locale: (typeof LOCALES)[number];
  setLocale: (next: (typeof LOCALES)[number]) => void;
  label: string;
}) {
  const index = LOCALES.indexOf(locale);
  const width = 100 / LOCALES.length;

  return (
    <div
      role="group"
      aria-label={label}
      data-no-retype
      className="relative flex items-center rounded-full border border-line bg-surface-sunken p-0.5"
    >
      <span
        aria-hidden
        className="absolute inset-y-0.5 rounded-full bg-surface shadow-sm ring-1 ring-line transition-transform duration-300 ease-out"
        style={{
          width: `calc(${width}% - 2px)`,
          left: "2px",
          transform: `translateX(${index * 100}%)`,
        }}
      />
      {LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLocale(code)}
          aria-pressed={locale === code}
          // A fixed width rather than padding: the sliding indicator is sized
          // as a fraction of the control, so the halves have to be equal or it
          // lands a pixel off the label it is meant to sit behind.
          className={`relative z-10 w-9 rounded-full py-1 text-center text-xs font-semibold uppercase tracking-wide transition-colors duration-200 ${
            locale === code ? "text-accent" : "text-ink-faint hover:text-ink"
          }`}
        >
          {code}
        </button>
      ))}
    </div>
  );
}

function GitHubMark() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="currentColor"
      className="size-[18px]"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

/** Three bars: the numbers, which is what the page behind this link is. */
function MetricsMark() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      className="size-[17px]"
    >
      <path d="M3 13V9M8 13V4M13 13v-6" />
    </svg>
  );
}
