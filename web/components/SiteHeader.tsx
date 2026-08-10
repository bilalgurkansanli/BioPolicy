"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AccountMenu } from "@/components/AccountMenu";
import { LeaveConfirm } from "@/components/LeaveConfirm";
import { useLocale } from "@/components/LocaleProvider";
import { SlideLink } from "@/components/SlideLink";
import { LOCALES } from "@/lib/i18n";

const REPO_URL = "https://github.com/bilalgurkansanli/BioPolicy";

/** Where this project sits among the others. Not part of this site. */
const PROJECTS_URL = "https://projects.bilalgurkansanli.com";

/**
 * The workspace is the point of the site, so it does not sit in a row of links:
 * it is a filled button on the right, with a slow halo behind it. Everything
 * else in the header is deliberately quieter.
 */
export function SiteHeader() {
  const { locale, setLocale, t } = useLocale();
  const pathname = usePathname();
  const [leaving, setLeaving] = useState(false);

  const onWorkspace = pathname === "/app";

  return (
    <header className="sticky top-0 z-30 transform-gpu border-b border-line bg-paper will-change-transform sm:bg-paper/80 sm:backdrop-blur-md">
      {/* Opaque on a phone, translucent from `sm` up.

          `backdrop-filter` on a sticky element makes the browser re-sample
          everything behind it on every frame of a scroll. On a desktop that is
          free; on a phone the compositor falls behind and the bar appears to
          slide down and snap back — which is exactly what it looked like.

          It is also the effect a 64px bar shows least of: there is very little
          behind it to see through. So the blur is spent where it is affordable
          and dropped where it is not.

          `transform-gpu` and `will-change-transform` are the second half. A
          sticky bar that shares a paint layer with the page is repainted with
          the page, and on a phone it arrives a frame late — which is seen as
          the bar drifting rather than as a dropped frame. Its own layer is
          moved by the compositor instead of redrawn.

          One consequence to keep in mind: both of these make this element a
          containing block for any `position: fixed` descendant. Nothing inside
          is fixed today — the leave dialog is portalled to `document.body`
          precisely because the blur already did this — and anything added later
          must be too. */}
      {/* `gap-2` below `sm`, not `gap-3`. The row had no room to spare on a
          phone, so adding anything to it has to take the space from somewhere,
          and four pixels of gap twice over is the cheapest thing in here to
          spend. Measured at 375px: with `gap-3` the row overflowed its own
          width by 8px, and `html { overflow-x: clip }` then hid the overflow —
          content cut off with no scrollbar to reveal that it had been, which is
          the worse half of that failure. With `gap-2` it fits.

          Below roughly 372px it overflows either way, with or without the link
          to the left. That predates this and is left alone rather than fixed by
          quietly shrinking somebody else's call-to-action. */}
      {/* Asymmetric on purpose, and only above the column width.
          The row *starts* at the viewport's left edge so the link out of the
          site sits in the corner, and *ends* where the centred `max-w-7xl`
          column ends so everything on the right stays exactly where it was.
          Making the whole row full width moved the right-hand controls out to
          the screen edge too, which was not what was wanted.
          Applied from `xl` only, which is the width above which the column
          stops spanning the viewport and the calc has anything to say. It was
          an inline style with a `max()` floor first, and an inline style beats
          the responsive classes: the row kept 24px of right padding against
          16px of left at every width, which cost eight pixels a phone does not
          have and pushed the header two past the screen. */}
      <div className="flex h-16 w-full items-center gap-2 px-4 sm:gap-5 sm:px-6 xl:[padding-right:calc((100vw-80rem)/2+1.5rem)]">
        {/* The way back out of the project entirely, left of the mark because
            that is where a step backwards belongs and because it is not part of
            this site — putting it in the row on the right would file it beside
            the pages of this project, which it is not.

            A plain anchor, not a SlideLink: the slide is this app's router
            moving between its own pages, and running it against a different
            origin would animate the page out and then sit on a blank frame
            while a full document load happens underneath.

            Same tab, no `target="_blank"`. "Back to projects" is a departure,
            and a departure that leaves the thing you departed from open behind
            you is not one. The label folds away on a phone for the same reason
            the wordmark does; the arrow keeps the meaning on its own. */}
        {/* Pulled out to the true left edge on a wide screen.
            `-ml-*` cancels the container's own padding so the link sits against
            the viewport rather than against the centred column — on a large
            monitor that column starts hundreds of pixels in, and a link meant
            to read as "out of here" placed there reads as part of the site's
            own navigation instead. Below `lg` the padding is left alone: on a
            phone the row needs every pixel of it. */}
        <a
          href={PROJECTS_URL}
          onClick={(event) => {
            // The dialog only exists on the narrow layout, and this is how it
            // knows: the same media query the label uses, asked in JS. Wide
            // screens keep the plain navigation — the sentence is right there,
            // and confirming something a reader has already read is friction.
            if (window.matchMedia("(max-width: 1023px)").matches) {
              event.preventDefault();
              setLeaving(true);
            }
          }}
          className="group -ml-1 inline-flex shrink-0 items-center gap-1.5 rounded-full px-1.5 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink sm:px-2.5"
        >
          <BackArrow />
          {/* The full invitation where there is room for it, the short form
              where there is less, the arrow alone where there is none.
              Measured rather than guessed: at 768 the row needs 743px without
              any label here and 877 with the short one, so a label at `md`
              overflows — which `html { overflow-x: clip }` then hides, cutting
              the call-to-action off with no scrollbar to say it had been. */}
          <span className="hidden xl:inline">{t.nav.backToProjects}</span>
          <span className="hidden lg:inline xl:hidden">
            {t.nav.backToProjectsShort}
          </span>
        </a>

        {/* The way out of the workspace, and the only one: the slide runs
            backwards here so leaving retraces the step that got you in. */}
        {/* `shrink-0` because the mark is an image with an aspect ratio, and a
            flex item that shrinks does not narrow it, it squashes it. Adding the
            link to the left of this took the logo from 26px wide to 6px on a
            phone — still 32 tall, so the shield simply became a sliver. Nothing
            in the row is elastic enough to absorb a squeeze correctly, so
            nothing in it should be asked to. */}
        {/* Set apart from the link to its left rather than butting against it.
            At the far left those two were 30px apart, which read as one control
            — an arrow, some words, then a mark — instead of as "leave the site"
            followed by "you are here". The gap is what separates them. */}
        <SlideLink
          href="/"
          direction="back"
          className="ml-6 flex shrink-0 items-center gap-2.5 lg:ml-16"
        >
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

        {/* The measurements, given the middle of the row to themselves.
            Everything used to sit in one cluster on the right — six controls
            abutting each other — and a row that dense reads as a toolbar rather
            than as navigation. Moving the one link that is a *destination* out
            of that cluster leaves four controls on the right instead of five
            and gives the eye somewhere to rest between the two ends.

            Centred on the *viewport* from `xl` up, not on the space the two
            ends leave. `mx-auto` does the latter, and because the two ends are
            different widths it lands left of the middle by however much they
            differ — close enough to look intentional and wrong enough to look
            off.

            Only from `xl`, because pinning to 50% takes it out of the flow and
            the flow is what was keeping it clear of the right-hand group.
            Measured at 768: centred it spans 315–453 while that group starts at
            273, so the two overlap. At 1280 the group starts at 785 and the
            link ends at 709. Below `xl` it goes back to sharing the row. */}
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
          className={`mx-auto hidden shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1.5 text-sm transition-colors hover:text-ink sm:inline-flex xl:absolute xl:left-1/2 xl:mx-0 xl:h-16 xl:-translate-x-1/2 xl:py-0 ${
            pathname === "/eval" ? "text-ink" : "text-ink-muted"
          }`}
        >
          <MetricsMark />
          {t.evaluation.title}
        </SlideLink>

        {/* The other half of the 320px fix. Four controls sit in here on a
            phone, so a gap costs three times over — 1.5 rather than 2 buys back
            six pixels that the row does not otherwise have. */}
        <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
          {/* Folds away on a phone, not just under 360px.

              Six controls do not fit a 360px row, which is the floor for every
              phone still being sold. Measured there: the right-hand group wants
              272px and cannot go below it, which leaves the header 17px over.
              Something has to go, and this is it — a repository link is for
              somebody about to read code, which is not what a phone is for, and
              the footer and the README both still carry it. Dropping it frees
              about 30px and the row fits with room to spare.

              The old rule was `max-[359px]:hidden`, which spared exactly the
              widths nobody has.

              Six controls do not fit a 320px row — measured at 337 needed
              against 320 available, after the gap and the language switch had
              already been tightened — so on those screens one of them has to
              go. This is the one: a repository link is for somebody who is
              going to read code, which is not what a 320px phone is for, and
              the footer and the README both still carry it.

              An exact `max-[359px]` rather than folding it at `sm`, because
              360px is the floor for every phone still being sold and the link
              should survive on all of them. */}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t.nav.source}
            className="hidden items-center gap-1.5 rounded-full px-2 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink sm:inline-flex sm:px-2.5"
          >
            <GitHubMark />
            <span className="hidden sm:inline">{t.nav.source}</span>
          </a>

          <LocaleSwitch locale={locale} setLocale={setLocale} label={t.language.label} />

          {/* Last but one, next to the button rather than first in the row.
              It used to lead the cluster, which put a personal control — an
              avatar, a menu that opens — at the point the eye lands first and
              made the whole right-hand side feel like an account area. It
              belongs beside the thing you do after signing in. */}
          <AccountMenu />

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
              {/* `inset-0`, not `-inset-1`. The four pixels it used to bleed on
                  each side were four pixels of *layout*: an absolutely
                  positioned child still counts toward its relative parent's
                  scrollable width, so the halo pushed the header row six pixels
                  past a 375px screen and `overflow-x: clip` cut the left edge
                  off the whole page. The glow is `filter: blur(10px)`, which
                  spreads well beyond the box on its own, so the box does not
                  need to. */}
              <span
                aria-hidden
                className="cta-halo absolute inset-0 rounded-full opacity-50"
              />
              <SlideLink
                href="/app"
                direction="forward"
                className="cta-gradient cta-sheen group relative inline-flex h-9 items-center gap-1 rounded-full pl-3 pr-2.5 text-sm font-semibold text-on-accent sm:gap-1.5 sm:pl-4 sm:pr-3.5 shadow-[0_6px_18px_-8px_var(--accent-glow)] hover:-translate-y-px hover:shadow-[0_12px_26px_-10px_var(--accent-glow)]"
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

      <LeaveConfirm
        open={leaving}
        onClose={() => setLeaving(false)}
        href={PROJECTS_URL}
        title={t.nav.leave.title}
        body={t.nav.leave.body}
        confirmLabel={t.nav.leave.confirm}
        cancelLabel={t.nav.leave.cancel}
      />
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
          // Narrower below `sm`, still equal halves so the indicator stays
          // aligned. At 320px the header ran 18px past its own width, and this
          // control was the widest thing in it that could give ground without
          // losing a feature — two letters do not need 36px to be legible.
          className={`relative z-10 w-7 rounded-full py-1 text-center text-xs font-semibold uppercase tracking-wide transition-colors duration-200 sm:w-9 ${
            locale === code ? "text-accent" : "text-ink-faint hover:text-ink"
          }`}
        >
          {code}
        </button>
      ))}
    </div>
  );
}

/**
 * Nudges left on hover, which is the whole affordance.
 *
 * The arrow moves rather than the label, so the text it sits beside does not
 * shift under a reader who is only passing over it. `motion-reduce` drops the
 * movement and leaves the colour change, which is enough on its own.
 */
function BackArrow() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-[15px] transition-transform group-hover:-translate-x-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
    >
      <path d="M10 3.5 5.5 8l4.5 4.5" />
    </svg>
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
