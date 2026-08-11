/**
 * The locale preference as an external store.
 *
 * `localStorage` genuinely is an external system — it outlives the React tree,
 * and another tab can change it underneath us — so it is read through
 * `useSyncExternalStore` rather than copied into state by an effect. That also
 * makes the server snapshot explicit, which is what keeps the first client
 * render from disagreeing with the HTML.
 */

import { DEFAULT_LOCALE, LOCALES, type Locale } from "./i18n";

const STORAGE_KEY = "biopolicy.locale";

const listeners = new Set<() => void>();
let snapshot: Locale | null = null;

function isLocale(value: string | null | undefined): value is Locale {
  return (
    typeof value === "string" && (LOCALES as readonly string[]).includes(value)
  );
}

function negotiate(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // Storage can be unavailable (private mode, blocked cookies). Falling
    // through to the browser's languages is better than failing to render.
  }
  // The browser's own list, in the order the visitor put it in. This is the
  // signal that decides whether somebody sees Turkish: a device set to Turkish
  // is the closest thing to "reads Turkish" that a page can know without
  // asking, and it costs no request and no location.
  for (const tag of navigator.languages ?? []) {
    const base = tag.slice(0, 2);
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}

function notify(): void {
  for (const listener of listeners) listener();
}

export function getLocaleSnapshot(): Locale {
  // Cached because `useSyncExternalStore` compares snapshots by identity and
  // calls this on every render.
  if (snapshot === null) snapshot = negotiate();
  return snapshot;
}

export function getServerLocaleSnapshot(): Locale {
  return DEFAULT_LOCALE;
}

export function setStoredLocale(next: Locale): void {
  snapshot = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // The choice still applies to this tab; it just will not be remembered.
  }
  notify();
}

export function subscribeToLocale(onChange: () => void): () => void {
  listeners.add(onChange);

  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    snapshot = null;
    notify();
  };
  window.addEventListener("storage", onStorage);

  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}
