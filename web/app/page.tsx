"use client";

import Link from "next/link";

import { useLocale } from "@/components/LocaleProvider";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

/**
 * The landing page leads with the refusal claim rather than with a feature
 * list, and puts the false-refusal rate next to the refusal accuracy. Showing
 * only the first would be showing the number that is trivially gamed by
 * refusing everything.
 */
export default function Home() {
  const { t } = useLocale();

  const numbers = [
    {
      value: "100%",
      label: t.landing.numbers.refusal,
      note: t.landing.numbers.refusalNote,
    },
    {
      value: "2%",
      label: t.landing.numbers.falseRefusal,
      note: t.landing.numbers.falseRefusalNote,
    },
    {
      value: "100%",
      label: t.landing.numbers.citations,
      note: t.landing.numbers.citationsNote,
    },
    {
      value: "98%",
      label: t.landing.numbers.recall,
      note: t.landing.numbers.recallNote,
    },
  ];

  return (
    <>
      <SiteHeader />

      <main className="flex-1">
        <section className="mx-auto w-full max-w-7xl px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
          <p className="text-xs font-medium uppercase tracking-widest text-ink-faint">
            {t.landing.eyebrow}
          </p>
          <h1 className="mt-5 max-w-3xl text-balance text-3xl font-semibold leading-[1.15] tracking-tight text-ink sm:text-5xl">
            {t.landing.thesis}
          </h1>
          <p className="mt-6 max-w-2xl text-pretty text-base leading-7 text-ink-muted sm:text-lg sm:leading-8">
            {t.landing.lede}
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/app"
              className="inline-flex h-11 items-center rounded-lg bg-ink px-5 text-sm font-medium text-paper transition-opacity hover:opacity-90"
            >
              {t.landing.ctaPrimary}
            </Link>
            <Link
              href="/eval"
              className="inline-flex h-11 items-center rounded-lg border border-line-strong px-5 text-sm font-medium text-ink transition-colors hover:bg-surface-sunken"
            >
              {t.landing.ctaSecondary}
            </Link>
          </div>
        </section>

        <section className="border-y border-line bg-surface">
          <div className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-6">
            <h2 className="text-sm font-medium text-ink">
              {t.landing.numbersTitle}
            </h2>
            <dl className="mt-6 grid gap-x-8 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
              {numbers.map((item) => (
                <div key={item.label} className="border-t border-line pt-4">
                  <dd className="font-mono text-3xl font-medium tabular-nums tracking-tight text-ink">
                    {item.value}
                  </dd>
                  <dt className="mt-1 text-sm font-medium text-ink">
                    {item.label}
                  </dt>
                  <p className="mt-1.5 text-xs leading-5 text-ink-faint">
                    {item.note}
                  </p>
                </div>
              ))}
            </dl>
            <p className="mt-8 max-w-2xl text-xs leading-5 text-ink-faint">
              {t.landing.numbersNote}{" "}
              <Link href="/eval" className="text-accent underline">
                {t.nav.evaluation}
              </Link>
            </p>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6">
          <h2 className="text-lg font-semibold tracking-tight text-ink">
            {t.landing.howTitle}
          </h2>
          <ol className="mt-8 grid gap-8 md:grid-cols-3">
            {t.landing.how.map((step, index) => (
              <li key={step.title} className="border-t border-line pt-4">
                <span className="font-mono text-xs text-ink-faint">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-2 text-base font-medium text-ink">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-ink-muted">
                  {step.body}
                </p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-line bg-surface">
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6">
            <h2 className="text-lg font-semibold tracking-tight text-ink">
              {t.landing.limitsTitle}
            </h2>
            <ul className="mt-6 max-w-3xl space-y-4">
              {t.landing.limits.map((limit) => (
                <li
                  key={limit}
                  className="flex gap-3 text-sm leading-6 text-ink-muted"
                >
                  <span
                    aria-hidden
                    className="mt-2.5 size-1 shrink-0 rounded-full bg-ink-faint"
                  />
                  {limit}
                </li>
              ))}
            </ul>
            <p className="mt-8 text-xs text-ink-faint">
              {t.landing.footerNote}
            </p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
