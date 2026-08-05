/**
 * The Supabase client, and the session behind every authenticated call.
 *
 * Sign-in is **anonymous** — see
 * [ADR 012](../../docs/adr/012-anonymous-accounts.md). A demo that deletes
 * everything after 24 hours has no business collecting an email address to do
 * it, and an account nobody asked for is a form between the visitor and the
 * thing they came to try.
 *
 * The client is what refreshes the token. Anonymous sessions expire like any
 * other, and a hand-rolled fetch holding one token would start returning 401s
 * an hour into a long session.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export class AuthUnavailableError extends Error {
  constructor(
    message: string,
    /** True when the project simply has anonymous sign-ins switched off. */
    readonly anonymousDisabled: boolean,
  ) {
    super(message);
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
      // No OAuth redirects to parse, and parsing them would mean touching the
      // URL on every page load for a flow this app does not have.
      detectSessionInUrl: false,
    },
  });
  return client;
}

/**
 * The current access token, signing in anonymously if there is no session.
 *
 * Called lazily rather than on page load: browsing the samples should not
 * create an account, and a visitor who never uploads never becomes a row in
 * `auth.users`.
 */
export async function accessToken(): Promise<string> {
  const supabase = getClient();

  const { data } = await supabase.auth.getSession();
  if (data.session?.access_token) return data.session.access_token;

  const { data: signedIn, error } = await supabase.auth.signInAnonymously();
  if (error || !signedIn.session) {
    // `anonymous_provider_disabled` is the one failure worth naming: it is a
    // project setting, not a bug, and the interface can say exactly which
    // switch is off instead of showing a generic sign-in failure.
    const disabled = error?.code === "anonymous_provider_disabled";
    throw new AuthUnavailableError(
      error?.message ?? "Could not start a session.",
      disabled,
    );
  }
  return signedIn.session.access_token;
}

/**
 * The access token if a session already exists, and `null` otherwise.
 *
 * Distinct from `accessToken()` because the difference is load-bearing: the
 * bundled samples are readable without an account, so fetching one must never
 * be the thing that creates a session — or that fails when anonymous sign-ins
 * are switched off, which would take the public demo down with it.
 */
export async function existingAccessToken(): Promise<string | null> {
  if (!isConfigured()) return null;
  const { data } = await getClient().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function currentUserId(): Promise<string | null> {
  if (!isConfigured()) return null;
  const { data } = await getClient().auth.getSession();
  return data.session?.user.id ?? null;
}
