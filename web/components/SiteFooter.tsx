"use client";

import { useLocale } from "@/components/LocaleProvider";

export function SiteFooter() {
  const { t } = useLocale();

  return (
    <footer className="border-t border-line bg-paper">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-6 text-xs text-ink-faint sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="max-w-xl">{t.footer.disclaimer}</p>
        <div className="flex items-center gap-4">
          {/* Retention is a promise, so it is stated on every page rather than
              buried in a privacy document nobody opens. */}
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1">
            <span
              aria-hidden
              className="size-1.5 rounded-full bg-good"
            />
            {t.footer.retention}
          </span>
          <span>{t.footer.license}</span>
        </div>
      </div>
    </footer>
  );
}
