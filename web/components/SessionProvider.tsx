"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { fetchMe } from "@/lib/api";
import {
  isConfigured,
  onAuthChange,
  signInWithGoogle,
  signOut as endSession,
  currentSession,
} from "@/lib/supabase";
import type { Me } from "@/lib/types";

type SessionValue = {
  /** False until the first session check has finished. */
  ready: boolean;
  signedIn: boolean;
  /** Account details and today's allowance, or `null` when signed out. */
  me: Me | null;
  configured: boolean;
  refresh: () => Promise<void>;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMe(await fetchMe());
    } catch {
      // A session that has expired between the check and the call. The gate
      // renders from `signedIn`, which the auth listener corrects on its own.
      setMe(null);
    }
  }, []);

  useEffect(() => {
    if (!isConfigured()) {
      void Promise.resolve().then(() => setReady(true));
      return;
    }

    // Two sources, because they answer different questions: the first tells us
    // what is true right now, the listener tells us when that stops being true
    // — including the moment the OAuth redirect lands back on this page.
    void (async () => {
      const session = await currentSession();
      setSignedIn(Boolean(session));
      if (session) await refresh();
      setReady(true);
    })();

    return onAuthChange((session) => {
      setSignedIn(Boolean(session));
      if (session) void refresh();
      else setMe(null);
    });
  }, [refresh]);

  const signIn = useCallback(async () => {
    // Back to the page they were on. Anything else loses the document they had
    // open, which is usually the reason they signed in.
    await signInWithGoogle(window.location.href);
  }, []);

  const signOut = useCallback(async () => {
    await endSession();
    setSignedIn(false);
    setMe(null);
  }, []);

  const value = useMemo(
    () => ({
      ready,
      signedIn,
      me,
      configured: isConfigured(),
      refresh,
      signIn,
      signOut,
    }),
    [ready, signedIn, me, refresh, signIn, signOut],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession must be used inside a SessionProvider");
  }
  return value;
}
