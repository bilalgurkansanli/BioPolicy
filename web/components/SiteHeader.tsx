"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useLocale } from "@/components/LocaleProvider";
import { LOCALES } from "@/lib/i18n";

const REPO_URL = "https://github.com/bilalgurkansanli/BioPolicy";

export function SiteHeader() {
  const { locale, setLocale, t } = useLocale();
  const pathname = usePathname();

  const links = [
    { href: "/app", label: t.nav.workspace },
    { href: "/eval", label: t.nav.evaluation },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-6 px-4 sm:px-6">
        <Link
          href="/"
          className="text-[15px] font-semibold tracking-tight text-ink"
        >
          Bio<span className="text-accent">Policy</span>
        </Link>

        <nav className="flex items-center gap-1 text-sm">
          {links.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-2.5 py-1.5 transition-colors ${
                  active
                    ? "bg-surface-sunken font-medium text-ink"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <div
            role="group"
            aria-label={t.language.label}
            className="flex items-center rounded-md border border-line p-0.5"
          >
            {LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLocale(code)}
                aria-pressed={locale === code}
                className={`rounded px-2 py-0.5 text-xs font-medium uppercase transition-colors ${
                  locale === code
                    ? "bg-ink text-paper"
                    : "text-ink-faint hover:text-ink"
                }`}
              >
                {code}
              </button>
            ))}
          </div>

          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden text-sm text-ink-muted transition-colors hover:text-ink sm:block"
          >
            {t.nav.source}
          </a>
        </div>
      </div>
    </header>
  );
}
