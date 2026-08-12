"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { dictionaries, type Dictionary, type Locale } from "@/lib/i18n";
import {
  getLocaleSnapshot,
  getServerLocaleSnapshot,
  setStoredLocale,
  subscribeToLocale,
} from "@/lib/locale-store";
import { replayText } from "@/lib/retype";
import { SITE_NAME } from "@/lib/site";

/**
 * Which dictionary key names each route, for the tab title.
 *
 * `/` is deliberately absent: its title is the whole sentence in `meta.title`
 * rather than a name fed through the `BioPolicy — %s` template, and handling it
 * as a special case is more honest than inventing a short name for it.
 *
 * A route missing from this map — the 404, anything added later — is left with
 * whatever Next rendered. A guessed title is worse than an untranslated one:
 * the first is wrong in a way nobody can see, the second is merely English.
 */
const PAGE_KEYS = {
  "/app": "app",
  "/eval": "eval",
  "/signin": "signin",
  "/privacy": "privacy",
  "/terms": "terms",
  "/cookies": "cookies",
} as const satisfies Record<string, keyof Dictionary["meta"]["pages"]>;

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Dictionary;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(
    subscribeToLocale,
    getLocaleSnapshot,
    getServerLocaleSnapshot,
  );

  // `<html lang>` is rendered on the server with the default locale, so it has
  // to be corrected once the preference is known. It matters for screen readers
  // and for hyphenation, both of which get Turkish badly wrong when told it is
  // English.
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  // The tab title, for the same reason and by the same means as `lang` above:
  // page metadata is resolved at build time, so the server has no way to know
  // this reader picked Turkish (ADR 011).
  //
  // Keyed on the route as well as the locale because Next writes its own title
  // on every client-side navigation. Without `pathname` here this would set the
  // title once and then watch Next replace it on the next link click.
  const pathname = usePathname();
  useEffect(() => {
    const meta = dictionaries[locale].meta;
    const key = PAGE_KEYS[pathname as keyof typeof PAGE_KEYS];
    // `/` carries the whole sentence rather than a name plus the template, and
    // the rest are assembled in the root layout's order. The two build the same
    // string by different routes, so a change to one is a change to both.
    const wanted =
      pathname === "/"
        ? meta.title
        : key
          ? `${SITE_NAME} — ${meta.pages[key]}`
          : null;
    if (wanted === null) return;

    const apply = () => {
      if (document.title !== wanted) document.title = wanted;
    };
    apply();

    // Setting it once is not enough, and which way it fails depends on how the
    // page was reached. Measured on a production build, first load of `/app`
    // with a Turkish browser:
    //
    //   hydration effects → we write "Çalışma alanı", React commits the
    //   build-time metadata after us → "Workspace" wins.
    //
    // On a client-side navigation the order is the other way round — Next
    // writes at 8353ms, we correct at 8358ms — so the same code that loses the
    // race on load wins it on every link click. React owns the `<title>` node;
    // we do not get to choose when it writes.
    //
    // So rather than guess at a delay that makes us last, watch the node and
    // reassert: whoever writes it, the reader's language is what stays. The
    // equality check in `apply` is what keeps our own write from re-entering
    // this observer.
    const observer = new MutationObserver(apply);
    observer.observe(document.head, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => observer.disconnect();
  }, [locale, pathname]);

  // Every visible string has just been replaced, so the page writes itself out
  // again. The first run is skipped: on a fresh load nothing was rewritten, and
  // an animation there would only delay the first paint of the real content.
  const isFirstLocale = useRef(true);
  useEffect(() => {
    if (isFirstLocale.current) {
      isFirstLocale.current = false;
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    replayText();
  }, [locale]);

  const value = useMemo(
    () => ({ locale, setLocale: setStoredLocale, t: dictionaries[locale] }),
    [locale],
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (value === null) {
    throw new Error("useLocale must be used inside a LocaleProvider");
  }
  return value;
}
