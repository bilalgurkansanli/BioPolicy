"use client";

import type { ReactNode } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { SlideLink } from "@/components/SlideLink";

/**
 * The landing page has one job: get someone into the workspace. It leads with
 * the refusal claim rather than a feature list, keeps the explanation to three
 * steps, and offers exactly one destination.
 */
export default function Home() {
  const { t } = useLocale();

  // One icon per step, in the order the pipeline runs: the document is read,
  // the two searches meet, the answer is checked against its source.
  const stepIcons = [<ParseIcon key="parse" />, <SearchIcon key="search" />, <ShieldIcon key="shield" />];

  return (
    <>
      <SiteHeader />

      <main className="flex-1">
        <section className="relative isolate overflow-hidden">
          <div
            aria-hidden
            className="hero-wash pointer-events-none absolute inset-0 -z-10"
          />
          <div
            aria-hidden
            className="hero-grid pointer-events-none absolute inset-0 -z-10 opacity-70"
          />

          {/* Wider than the lede below it: the headline is set at 60px, and at
              max-w-3xl the English second sentence wrapped for the sake of ~30
              pixels. The body copy keeps its own narrower measure. */}
          <div className="mx-auto w-full max-w-4xl px-4 pb-24 pt-20 text-center sm:px-6 sm:pb-32 sm:pt-28">
            <span className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface/70 px-3.5 py-1.5 text-xs font-medium text-ink-muted backdrop-blur">
              <span
                aria-hidden
                className="size-1.5 rounded-full bg-gradient-to-br from-accent-fill-from to-accent-fill-to"
              />
              {t.landing.eyebrow}
            </span>

            {/* One block per sentence, so the break falls where the tagline is
                written to break. Each line still balances internally, which is
                what the Turkish second sentence needs at this size.

                No margin between the two blocks, and that is deliberate. At
                `text-6xl` with `leading-[1.1]` the line box already carries the
                space; adding `mt-3` on top of it opened a gap wide enough that
                the couplet stopped reading as one thought and became two
                stranded sentences. The leading is the spacing.

                The product name briefly sat above these lines, to satisfy a
                Google brand check that wants the app's name on its home page.
                It is gone: it read as a stray label over the thing it was
                labelling, and the check is unhappy for reasons that turned out
                to have nothing to do with this heading. The name is still on the
                page in the `What BioPolicy is` section below, in the header
                wordmark, and in the title. */}
            <h1 className="mt-7 text-balance text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-6xl">
              {t.landing.thesis.map((line) => (
                <span key={line} className="block">
                  {line}
                </span>
              ))}
            </h1>

            <p className="mx-auto mt-6 max-w-xl text-pretty text-base leading-7 text-ink-muted sm:text-lg sm:leading-8">
              {t.landing.lede}
            </p>

            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <SlideLink
                href="/app"
                direction="forward"
                className="cta-gradient cta-sheen accent-glow group inline-flex h-12 w-full items-center justify-center gap-2 rounded-full px-7 text-[15px] font-semibold text-on-accent hover:-translate-y-0.5 sm:w-auto"
              >
                <span>{t.landing.ctaPrimary}</span>
                <Arrow />
              </SlideLink>
              {/* The secondary action stays on the page rather than leading off
                  it: someone who is not ready to click the button should end up
                  further down this page, not somewhere else. */}
              <a
                href="#how"
                className="inline-flex h-12 w-full items-center justify-center rounded-full border border-line-strong bg-surface/70 px-7 text-[15px] font-medium text-ink backdrop-blur transition-colors hover:border-accent hover:text-accent sm:w-auto"
              >
                {t.landing.ctaSecondary}
              </a>
            </div>

            <p className="mt-5 text-xs text-ink-faint">{t.landing.ctaNote}</p>
          </div>
        </section>

        {/* The plain statement of what this is, above the fold's fold and
            before the pipeline explainer.

            It reads as ordinary copy, and it is also what an OAuth branding
            review is looking for: the application's name and purpose in prose,
            on the page the consent screen points at. Everything above this
            works by implication — a tagline is a promise, not a definition —
            and the only place the name appeared was a header wordmark that is
            `hidden` below `sm`. */}
        <section
          id="about"
          className="mx-auto w-full max-w-3xl scroll-mt-20 px-4 pb-10 pt-2 sm:px-6"
        >
          <h2 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">
            {t.landing.about.title}
          </h2>
          <p className="mt-4 text-pretty text-[15px] leading-7 text-ink-muted">
            {t.landing.about.body}
          </p>
          <p className="mt-3 text-pretty text-sm leading-6 text-ink-faint">
            {t.landing.about.signIn}
          </p>
        </section>

        <section
          id="how"
          className="mx-auto w-full max-w-5xl scroll-mt-20 px-4 pb-4 pt-4 sm:px-6"
        >
          <h2 className="text-center text-xl font-semibold tracking-tight text-ink sm:text-2xl">
            {t.landing.howTitle}
          </h2>
          <ol className="mt-10 grid gap-5 md:grid-cols-3">
            {t.landing.how.map((step, index) => (
              <li
                key={step.title}
                className="group rounded-3xl border border-line bg-surface p-7 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[0_18px_40px_-30px_var(--accent-glow)]"
              >
                {/* The mark's counters are perfect circles, so the steps carry
                    the same geometry rather than a softened square. */}
                <span
                  aria-hidden
                  className="inline-flex size-12 items-center justify-center rounded-full bg-accent-soft text-accent ring-1 ring-accent/15 transition-colors duration-200 group-hover:bg-gradient-to-br group-hover:from-accent-fill-from group-hover:to-accent-fill-to group-hover:text-on-accent"
                >
                  {stepIcons[index]}
                </span>
                <h3 className="mt-4 text-base font-semibold text-ink">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-ink-muted">
                  {step.body}
                </p>
              </li>
            ))}
          </ol>
        </section>

        <section className="mx-auto w-full max-w-5xl px-4 py-20 sm:px-6">
          <div className="relative isolate overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-accent-fill-from to-accent-fill-to px-6 py-14 text-center sm:px-12">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60%_80%_at_20%_0%,rgb(255_255_255_/_0.22),transparent_70%)]"
            />
            <h2 className="text-balance text-2xl font-semibold tracking-tight text-on-accent sm:text-3xl">
              {t.landing.closingTitle}
            </h2>
            <p className="mx-auto mt-4 max-w-lg text-pretty text-sm leading-6 text-on-accent/80 sm:text-base">
              {t.landing.closingBody}
            </p>
            <SlideLink
              href="/app"
              direction="forward"
              className="group mt-8 inline-flex h-12 items-center justify-center gap-2 rounded-full bg-surface px-7 text-[15px] font-semibold text-accent shadow-lg transition-transform duration-200 hover:-translate-y-0.5"
            >
              {t.nav.workspace}
              <Arrow />
            </SlideLink>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}

/** The arrow leans forward on hover, so the button reads as a door, not a label. */
function Arrow() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
    >
      <path
        d="M3 8h10m0 0-4-4m4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconFrame({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-5"
    >
      {children}
    </svg>
  );
}

/** A page with lines of text on it: the document being read. */
function ParseIcon() {
  return (
    <IconFrame>
      <path d="M6 3h8l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M14 3v5h4" />
      <path d="M8.5 12h7M8.5 15.5h7M8.5 19h4" />
    </IconFrame>
  );
}

/** Two overlapping lenses: the semantic and the keyword search, run together. */
function SearchIcon() {
  return (
    <IconFrame>
      <circle cx="10" cy="10" r="5" />
      <circle cx="15" cy="14" r="5" />
      <path d="M18.6 17.6 21.5 20.5" />
    </IconFrame>
  );
}

/** A shield with a tick: the answer that failed its check is never shown. */
function ShieldIcon() {
  return (
    <IconFrame>
      <path d="M12 2.8 4.8 5.6v5.9c0 4.4 3 7.9 7.2 9.7 4.2-1.8 7.2-5.3 7.2-9.7V5.6L12 2.8Z" />
      <path d="m9 12 2.2 2.2L15.4 10" />
    </IconFrame>
  );
}
