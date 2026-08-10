"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { SlideLink } from "@/components/SlideLink";
import { LOCALES } from "@/lib/i18n";

/**
 * The header's overflow, on a phone only.
 *
 * Six controls do not fit a 320px row. Hiding the two that lost — the
 * evaluation and the repository — put them out of reach on the device most
 * people arrive on, and squeezing the language switch to 28px left a target
 * nobody can hit reliably, which reads as a button that does not work rather
 * than one that was missed.
 *
 * So they move behind one control instead of competing for the row. What is
 * left outside is what a visitor needs *now*: the way out, the mark, their
 * account, and the one thing the page is asking them to do.
 *
 * Every item in here is at least 44px tall. That is the point of the menu as
 * much as the space is: a list has room for proper targets and a row does not.
 */
export function HeaderMenu({ repoUrl }: { repoUrl: string }) {
  const { locale, setLocale, t } = useLocale();
  const wrapper = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  // The route the menu was opened on travels with the open flag, so a
  // navigation closes it without an effect. `SlideLink` takes no `onClick`, and
  // the route is the better trigger anyway: the menu should close because the
  // page changed, not because one particular item was the thing tapped.
  //
  // Adjusted during render rather than in an effect. That is the pattern React
  // documents for state that has to follow a prop, and the one
  // `react-hooks/set-state-in-effect` exists to steer toward — the alternative
  // renders the stale value first and corrects it on a second pass.
  const [menu, setMenu] = useState({ open: false, at: pathname });
  if (menu.at !== pathname) setMenu({ open: false, at: pathname });
  const open = menu.open && menu.at === pathname;
  const setOpen = (next: boolean | ((was: boolean) => boolean)) =>
    setMenu((current) => ({
      at: pathname,
      open: typeof next === "function" ? next(current.open) : next,
    }));

  // Closes on an outside tap and on Escape. Bound while open only, so a closed
  // menu costs nothing.
  useEffect(() => {
    if (!open) return;

    const close = () => setMenu((current) => ({ ...current, open: false }));
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      // Both, because the panel is no longer a descendant of the wrapper: it
      // hangs off the header so it can reach the screen's edge.
      if (!wrapper.current?.contains(target) && !panel.current?.contains(target)) {
        close();
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapper} className="sm:hidden">
      <button
        type="button"
        aria-label={t.nav.menu}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((was) => !was)}
        className="flex size-9 items-center justify-center rounded-full border border-line text-ink-muted transition-colors hover:text-ink"
      >
        <svg aria-hidden viewBox="0 0 16 16" fill="currentColor" className="size-4">
          <circle cx="3" cy="8" r="1.4" />
          <circle cx="8" cy="8" r="1.4" />
          <circle cx="13" cy="8" r="1.4" />
        </svg>
      </button>

      {open && (
        // Absolute, not fixed. The header carries `transform-gpu`, which makes
        // it the containing block for a fixed child — a dropdown pinned that way
        // would resolve against the 64px bar. Absolute against this wrapper is
        // what it wants anyway.
        //
        // Hung from the header rather than from the button's own wrapper. Two
        // controls sit between the button and the edge, so a panel anchored to
        // it starts well inside the row — measured at 320px, a 208px panel
        // began 38px off the left of the screen and a 156px one still began at
        // -4. Anchored to the header it hangs from the screen's right margin,
        // where there is room for it whatever sits to the button's right.
        <div
          ref={panel}
          role="menu"
          className="menu-pop absolute right-4 top-full z-40 mt-2 w-48 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-line bg-surface shadow-[0_24px_50px_-24px_rgb(0_0_0_/_0.6)]"
        >
          <SlideLink
            href="/eval"
            direction="forward"
            role="menuitem"
            className="flex min-h-11 items-center px-4 text-sm text-ink transition-colors hover:bg-surface-sunken"
          >
            {t.evaluation.title}
          </SlideLink>

          <a
            href={repoUrl}
            target="_blank"
            rel="noopener noreferrer"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex min-h-11 items-center border-t border-line px-4 text-sm text-ink transition-colors hover:bg-surface-sunken"
          >
            {t.nav.source}
          </a>

          <div className="flex items-center gap-2 border-t border-line px-4 py-2.5">
            <span className="text-xs text-ink-faint">{t.language.label}</span>
            <div className="ml-auto flex gap-1">
              {LOCALES.map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => {
                    setLocale(code);
                    setOpen(false);
                  }}
                  aria-pressed={locale === code}
                  className={`size-9 rounded-full text-xs font-semibold uppercase transition-colors ${
                    locale === code
                      ? "bg-accent-soft text-accent"
                      : "text-ink-muted hover:bg-surface-sunken"
                  }`}
                >
                  {code}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
