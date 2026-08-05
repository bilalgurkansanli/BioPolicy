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

import { deleteAccount as eraseAccount, fetchMe } from "@/lib/api";
import {
  isConfigured,
  onAuthChange,
  profileOf,
  signInWithGoogle,
  signOut as endSession,
  currentSession,
  type Profile,
} from "@/lib/supabase";
import type { Me } from "@/lib/types";

type SessionValue = {
  /** False until the first session check has finished. */
  ready: boolean;
  signedIn: boolean;
  /** Account details and today's allowance, or `null` when signed out. */
  me: Me | null;
  /** Name and picture, from the identity provider rather than our database. */
  profile: Profile | null;
  configured: boolean;
  refresh: () => Promise<void>;
  /** Where to come back to after Google. Defaults to the current page. */
  signIn: (returnTo?: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Erase the account, then end the session it was signed in with. */
  deleteAccount: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

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
      setProfile(profileOf(session));
      if (session) await refresh();
      setReady(true);
    })();

    return onAuthChange((session) => {
      setSignedIn(Boolean(session));
      setProfile(profileOf(session));
      if (session) void refresh();
      else setMe(null);
    });
  }, [refresh]);

  const signIn = useCallback(async (returnTo?: string) => {
    // Back to the page they were on, by default: anything else loses the
    // document they had open, which is usually the reason they signed in. The
    // sign-in screen is the exception — coming back to it would be arriving
    // where there is nothing left to do.
    await signInWithGoogle(
      returnTo
        ? new URL(returnTo, window.location.origin).href
        : window.location.href,
    );
  }, []);

  const signOut = useCallback(async () => {
    await endSession();
    setSignedIn(false);
    setMe(null);
    setProfile(null);
  }, []);

  const deleteAccount = useCallback(async () => {
    // The call needs the session's token, so it goes first and the session is
    // ended only once the account is actually gone. A failure here leaves the
    // visitor signed in to an account that still exists, which is the truth.
    await eraseAccount();
    await endSession();
    setSignedIn(false);
    setMe(null);
    setProfile(null);
  }, []);

  const value = useMemo(
    () => ({
      ready,
      signedIn,
      me,
      profile,
      configured: isConfigured(),
      refresh,
      signIn,
      signOut,
      deleteAccount,
    }),
    [ready, signedIn, me, profile, refresh, signIn, signOut, deleteAccount],
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
