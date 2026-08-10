"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useLocale } from "@/components/LocaleProvider";
import { SlideLink } from "@/components/SlideLink";

const REPO_URL = "https://github.com/bilalgurkansanli/BioPolicy";

export function SiteFooter() {
  const { t } = useLocale();
  const pathname = usePathname();

  return (
    <footer className="border-t border-line bg-paper">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-6 text-xs text-ink-faint sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="max-w-xl">{t.footer.disclaimer}</p>
        {/* Wraps. Five items — three links, the retention promise and the
            licence — do not fit a phone's width on one line, and without
            `flex-wrap` they do not go anywhere: they shrink past their own text
            and print over each other. `gap-y` is what keeps the wrapped rows
            apart once they are allowed to exist. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {/* The measurements are reachable but quiet: they are the project's
              evidence, not its invitation, and a second link beside the header's
              call-to-action would compete with the one thing it asks for. */}
          {/* Same destination as the header's link, so the same rule decides
              which way the page moves — see SiteHeader. Two links to one page
              that animate differently would read as two different places. */}
          {/* `-my-2 py-2` grows the tap target without moving anything. At the
              footer's 12px type this link was 16px tall, under the 24px minimum
              a pointer target is meant to meet — on a phone that is a link you
              aim at rather than press. The negative margin cancels the padding
              in layout, so the row keeps its height and only the hit area
              changes. It is a standalone link rather than one inside a
              sentence, so the inline exception does not apply to it. */}
          <SlideLink
            href="/eval"
            direction={pathname === "/app" ? "back" : "forward"}
            className="-my-2 py-2 underline-offset-4 transition-colors hover:text-ink hover:underline"
          >
            {t.evaluation.title}
          </SlideLink>
          {/* Retention is a promise, so it is stated on every page rather than
              buried in a privacy document nobody opens. */}
          {/* Same `-my-2 py-2` reasoning as the link above: at 12px type these
              would be 16px targets, under the 24px minimum. */}
          <Link
            href="/privacy"
            className="-my-2 py-2 underline-offset-4 transition-colors hover:text-ink hover:underline"
          >
            {t.footer.privacy}
          </Link>
          <Link
            href="/terms"
            className="-my-2 py-2 underline-offset-4 transition-colors hover:text-ink hover:underline"
          >
            {t.footer.terms}
          </Link>
          <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line px-2.5 py-1">
            <span
              aria-hidden
              className="size-1.5 rounded-full bg-good"
            />
            {t.footer.retention}
          </span>
          {/* The header folds this away on a phone because six controls do not
              fit the row, which left it reachable from nowhere at all on the
              device most people arrive on. Here it costs nothing: the footer
              wraps, so one more item is one more item on a new line. */}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="-my-2 py-2 underline-offset-4 transition-colors hover:text-ink hover:underline"
          >
            {t.nav.source}
          </a>
          <span>{t.footer.license}</span>
        </div>
      </div>
    </footer>
  );
}
