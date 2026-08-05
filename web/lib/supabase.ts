/**
 * The Supabase client, and the session behind every authenticated call.
 *
 * Sign-in is **Google, and only Google** — see
 * [ADR 013](../../docs/adr/013-google-only-sign-in.md). One provider means one
 * way in to audit, and it is what makes an email address on an account row
 * strong enough to hang the usage allowlist on.
 *
 * The client owns the session and refreshes it. Tokens expire in an hour, and a
 * hand-rolled fetch holding one would start returning 401s partway through a
 * long visit.
 */

import {
  createClient,
  type Session,
  type SupabaseClient,
} from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export class AuthUnavailableError extends Error {
  constructor(
    message: string,
    /** True when the project simply has Google sign-in switched off. */
    readonly providerDisabled: boolean,
  ) {
    super(message);
  }
}

/** Thrown by authenticated calls made with no session. Callers show the gate. */
export class NotSignedInError extends Error {
  constructor() {
    super("Not signed in.");
  }
}

let client: SupabaseClient | null = null;

export function isConfigured(): boolean {
  return Boolean(url && anonKey);
}

function getClient(): SupabaseClient {
  if (!isConfigured()) {
    throw new AuthUnavailableError("Supabase is not configured.", false);
  }
  client ??= createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      // The OAuth redirect comes back with the session in the URL, so unlike
      // the anonymous flow this must be read and cleared on load.
      detectSessionInUrl: true,
      flowType: "pkce",
    },
  });
  return client;
}

export type Account = { id: string; email: string | null };

/** What Google told us about the person, for the header. */
export type Profile = {
  name: string | null;
  email: string | null;
  /** Google's avatar URL, or `null` when the account has no picture. */
  avatar: string | null;
};

export function profileOf(session: Session | null): Profile | null {
  if (!session) return null;
  // Google fills `avatar_url` and `full_name`; the OIDC spelling of both is
  // there too on some accounts, so read either rather than showing a blank.
  const meta = (session.user.user_metadata ?? {}) as Record<string, unknown>;
  const pick = (...keys: string[]): string | null => {
    for (const key of keys) {
      const value = meta[key];
      if (typeof value === "string" && value.trim()) return value;
    }
    return null;
  };

  return {
    name: pick("full_name", "name"),
    email: session.user.email ?? pick("email"),
    avatar: pick("avatar_url", "picture"),
  };
}

export async function currentSession(): Promise<Session | null> {
  if (!isConfigured()) return null;
  const { data } = await getClient().auth.getSession();
  return data.session ?? null;
}

/**
 * The access token, or `null` when nobody is signed in.
 *
 * Never signs anyone in as a side effect. Sign-in leaves the page for Google
 * and comes back, so it cannot be something that happens quietly underneath a
 * fetch — it has to be a thing the visitor chose.
 */
export async function accessToken(): Promise<string | null> {
  return (await currentSession())?.access_token ?? null;
}

/**
 * Whether the project actually has Google switched on.
 *
 * Asked *before* leaving the page, because the failure otherwise happens on the
 * far side of a redirect: `signInWithOAuth` builds its URL locally and always
 * succeeds, and Supabase only rejects a disabled provider when the browser
 * arrives at `/authorize` — where the visitor is shown raw JSON on a domain
 * that is not ours. One cheap call turns that into a sentence naming the
 * setting.
 */
export async function googleEnabled(): Promise<boolean> {
  if (!isConfigured()) return false;
  try {
    const response = await fetch(`${url}/auth/v1/settings`, {
      headers: { apikey: anonKey },
    });
    if (!response.ok) return true; // unknown; let the real attempt decide
    const settings = await response.json();
    return Boolean(settings?.external?.google);
  } catch {
    // Offline, or the endpoint moved. Not a reason to block sign-in.
    return true;
  }
}

export async function signInWithGoogle(redirectTo: string): Promise<void> {
  if (!(await googleEnabled())) {
    throw new AuthUnavailableError("Google provider is not enabled.", true);
  }

  const { error } = await getClient().auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo,
      // Google returns a refresh token only when asked, and only the first
      // time, unless consent is requested again. Without it the session dies
      // after an hour and the visitor is signed out mid-conversation.
      queryParams: { access_type: "offline", prompt: "consent" },
    },
  });
  if (error) {
    // `provider is not enabled` is the one failure worth naming: it is a
    // project setting, not a bug, and the interface can point at the switch.
    const disabled = /provider.*(not enabled|disabled)/i.test(error.message);
    throw new AuthUnavailableError(error.message, disabled);
  }
}

export async function signOut(): Promise<void> {
  if (!isConfigured()) return;
  await getClient().auth.signOut();
}

/** Fires whenever the session appears, refreshes or goes away. */
export function onAuthChange(handler: (session: Session | null) => void): () => void {
  if (!isConfigured()) return () => undefined;
  const { data } = getClient().auth.onAuthStateChange((_event, session) => {
    handler(session);
  });
  return () => data.subscription.unsubscribe();
}
