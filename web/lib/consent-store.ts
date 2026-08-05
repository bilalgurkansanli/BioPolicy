/**
 * Whether the visitor has agreed to the measurement cookie.
 *
 * An external store rather than React state for the same reason the locale is
 * one: it outlives the tree, another tab can change it, and the answer is
 * needed before anything is rendered. `"unset"` is a real third value — it is
 * the state in which the banner is shown and nothing is loaded, and collapsing
 * it into "denied" would mean never asking.
 *
 * Consent is stored, never assumed. Analytics load only on `"granted"`.
 */

const STORAGE_KEY = "biopolicy.consent";

export type Consent = "granted" | "denied" | "unset";

const listeners = new Set<() => void>();
let snapshot: Consent | null = null;

function read(): Consent {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "granted" || stored === "denied" ? stored : "unset";
  } catch {
    // Storage blocked. Nothing was agreed to, so nothing is loaded.
    return "unset";
  }
}

export function getConsentSnapshot(): Consent {
  // Cached because `useSyncExternalStore` compares by identity and calls this
  // on every render.
  if (snapshot === null) snapshot = read();
  return snapshot;
}

export function getServerConsentSnapshot(): Consent {
  // The server cannot know, and guessing "granted" would load a tracker for
  // somebody who has not answered yet.
  return "unset";
}

export function setConsent(next: Exclude<Consent, "unset">): void {
  snapshot = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // The choice still applies to this tab; it just will not be remembered.
  }
  for (const listener of listeners) listener();
}

/** Back to never-asked, so the banner returns and the choice can be remade. */
export function clearConsent(): void {
  snapshot = "unset";
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing was stored to begin with.
  }
  for (const listener of listeners) listener();
}

export function subscribeToConsent(onChange: () => void): () => void {
  listeners.add(onChange);

  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    snapshot = null;
    for (const listener of listeners) listener();
  };
  window.addEventListener("storage", onStorage);

  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}
