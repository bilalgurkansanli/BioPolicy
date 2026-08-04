"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
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
