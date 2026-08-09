"use client";

import Link from "next/link";

import { useLocale } from "@/components/LocaleProvider";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { legalDocument, type LegalDocument } from "@/lib/legal";

/**
 * One renderer for all three legal documents.
 *
 * Client-rendered because the language is a client preference — the same URL has
 * to serve either language without a round trip, the way every other page here
 * does. That costs the SEO value of server-rendered legal text, which these
 * pages do not need: they exist to be read and linked, not found in search.
 */
export function LegalPage({ slug }: { slug: LegalDocument["slug"] }) {
  const { locale, t } = useLocale();
  const document = legalDocument(slug, locale);
  const siblings = (["privacy", "terms", "cookies"] as const).filter(
    (other) => other !== slug,
  );

  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <SiteHeader />
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-10 sm:px-6 sm:py-14">
      <p className="font-mono text-xs text-ink-faint">
        {t.legal.updated} {document.updated}
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
        {document.title}
      </h1>
      <p className="mt-2 text-sm leading-6 text-ink-muted">{document.lede}</p>

      <div className="mt-8 space-y-8">
        {document.sections.map((section) => (
          <section key={section.heading}>
            <h2 className="text-base font-medium text-ink">{section.heading}</h2>
            {section.body.map((paragraph) => (
              <p
                key={paragraph.slice(0, 40)}
                className="mt-2 text-sm leading-7 text-ink-muted"
              >
                {paragraph}
              </p>
            ))}
            {section.bullets && (
              <ul className="mt-3 space-y-1.5">
                {section.bullets.map((bullet) => (
                  <li
                    key={bullet.slice(0, 40)}
                    className="flex gap-2 text-sm leading-6 text-ink-muted"
                  >
                    <span aria-hidden className="text-ink-faint">
                      ·
                    </span>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      <nav className="mt-12 flex flex-wrap gap-x-5 gap-y-2 border-t border-line pt-5 text-sm">
        {siblings.map((other) => (
          <Link
            key={other}
            href={`/${other}`}
            className="text-accent underline-offset-4 hover:underline"
          >
            {legalDocument(other, locale).title}
          </Link>
        ))}
        <Link
          href="/"
          className="text-ink-faint underline-offset-4 hover:text-ink hover:underline"
        >
          {t.legal.home}
        </Link>
        </nav>
      </main>
      <SiteFooter />
    </div>
  );
}
