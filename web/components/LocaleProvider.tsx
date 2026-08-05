"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";

const RETYPE_CLASS = "locale-retype";
const RETYPE_MS = 620;

import { dictionaries, type Dictionary, type Locale } from "@/lib/i18n";
import {
  getLocaleSnapshot,
  getServerLocaleSnapshot,
  setStoredLocale,
  subscribeToLocale,
} from "@/lib/locale-store";

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

  // Every visible string has just been replaced, so the page replays itself.
  // The first run is skipped: on a fresh load nothing was rewritten, and an
  // animation there would only delay the first paint of the real content.
  const isFirstLocale = useRef(true);
  useEffect(() => {
    if (isFirstLocale.current) {
      isFirstLocale.current = false;
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const { body } = document;
    // Removing the class and reading a layout value in between is what lets the
    // animation restart when the language is switched twice in a row.
    body.classList.remove(RETYPE_CLASS);
    void body.offsetWidth;
    body.classList.add(RETYPE_CLASS);

    const timer = window.setTimeout(
      () => body.classList.remove(RETYPE_CLASS),
      RETYPE_MS,
    );
    return () => {
      window.clearTimeout(timer);
      body.classList.remove(RETYPE_CLASS);
    };
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
