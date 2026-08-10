import type { NextConfig } from "next";

/**
 * The FastAPI backend is a separate Vercel deployment (see docs/adr/006). This
 * rewrite is what makes it *look* same-origin to the browser: no CORS preflight
 * on any call, no third-party cookie question for Supabase auth, and the
 * `Authorization` header passes through untouched.
 *
 * In development this points at a locally running uvicorn.
 */
const API_ORIGIN =
  process.env.API_ORIGIN?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

const IS_DEV = process.env.NODE_ENV !== "production";

/**
 * Content-Security-Policy, assembled from what this app actually talks to.
 *
 * ## Why it is built rather than written out
 *
 * Two of the origins below are deployment-specific: the Supabase project, and
 * the analytics tag that only some deployments configure. A hand-written policy
 * would have to name every project anyone might deploy, which is a policy that
 * permits more than any single deployment needs — and on the analytics host, one
 * that opens a third party on installations that deliberately have no analytics.
 *
 * **This runs at build time, not per request.** Next.js evaluates `headers()`
 * during the build and writes the result into the routes manifest, so changing
 * `NEXT_PUBLIC_SUPABASE_URL` or the analytics id in a running deployment's
 * environment does not change the policy it serves. That needs a rebuild, and
 * on a platform that rebuilds on every deploy it is the ordinary case — but a
 * config change alone will look like it did nothing.
 *
 * ## `'unsafe-inline'` on scripts, stated plainly
 *
 * Next.js inlines its bootstrap and its flight data as `<script>` tags, so
 * without a nonce this directive cannot be tightened. Nonces need middleware
 * running per request, and every page here is statically rendered — that trade
 * (dynamic rendering on every route) buys protection against an injected inline
 * script, and this app renders no untrusted HTML: React escapes everything, and
 * the single `dangerouslySetInnerHTML` is fed a constant.
 *
 * So the value here is not in `script-src`. It is in the directives underneath
 * it, and those are the ones that matter for a product holding people's
 * insurance policies:
 *
 * * **`connect-src`** — an exfiltration channel has to be an allowed origin.
 *   A document's text cannot be POSTed to an attacker's host.
 * * **`frame-ancestors 'none'`** — clickjacking, and the modern half of the
 *   `X-Frame-Options` header already set below.
 * * **`object-src 'none'`** — no plugin content in an app whose whole job is
 *   opening files somebody uploaded.
 * * **`base-uri 'self'`** — an injected `<base>` cannot silently repoint every
 *   relative URL on the page.
 * * **`form-action 'self'`** — no form on this origin can post credentials
 *   somewhere else.
 */
function contentSecurityPolicy(): string {
  const supabase = originOf(process.env.NEXT_PUBLIC_SUPABASE_URL);

  // Only opened on deployments that configured the tag. The consent banner
  // decides whether it *loads*; this decides whether it is even permitted, so
  // an installation with analytics switched off does not carry a third-party
  // script origin in its policy. The id is validated the same way the component
  // validates it, because an id is not a URL and a malformed one here would
  // widen the policy rather than narrow it.
  const clarityConfigured = /^[a-z0-9]+$/i.test(
    process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID ?? "",
  );
  const clarity = clarityConfigured ? ["https://*.clarity.ms"] : [];

  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "base-uri": ["'self'"],
    "object-src": ["'none'"],
    "frame-ancestors": ["'none'"],
    "frame-src": ["'none'"],
    "form-action": ["'self'"],
    // `'unsafe-eval'` is React Refresh in development only. It is not in the
    // production policy, and a build that leaks it there is a bug.
    "script-src": [
      "'self'",
      "'unsafe-inline'",
      ...(IS_DEV ? ["'unsafe-eval'"] : []),
      ...clarity,
    ],
    "style-src": ["'self'", "'unsafe-inline'"],
    // `blob:` is the rendered PDF page; `data:` is the inline icon set.
    "img-src": ["'self'", "data:", "blob:", "https://*.googleusercontent.com", ...clarity],
    "font-src": ["'self'", "data:"],
    // pdf.js runs its parser off the main thread. The worker is served from
    // `public/`, and pdf.js falls back to a blob-wrapped copy of it.
    "worker-src": ["'self'", "blob:"],
    "manifest-src": ["'self'"],
    // `'self'` covers the API, which the browser reaches through the rewrite
    // above and therefore same-origin. Supabase is direct: the auth client
    // talks to it, and the PDF viewer fetches the signed storage URL from it.
    // `ws:` is the development HMR socket.
    "connect-src": ["'self'", ...supabase, ...(IS_DEV ? ["ws:"] : []), ...clarity],
  };

  const policy = Object.entries(directives)
    .map(([name, values]) => `${name} ${values.join(" ")}`)
    .join("; ");

  return IS_DEV ? policy : `${policy}; upgrade-insecure-requests`;
}

/**
 * The origin of a configured URL, or nothing.
 *
 * Returning an empty list for an unset or malformed value is deliberate: the
 * failure mode of guessing is a policy naming an origin nobody uses, and the
 * failure mode of returning nothing is a visible, immediate CSP violation in
 * the console — which is the one that gets fixed.
 */
function originOf(value: string | undefined): string[] {
  if (!value) return [];
  try {
    return [new URL(value).origin];
  } catch {
    return [];
  }
}

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // The browser must never see a Vercel-generated hint about the stack.
  poweredByHeader: false,

  async rewrites() {
    return {
      // WHY beforeFiles rather than the default (afterFiles): `/api/*` belongs
      // to the Python service, always. Resolving it before the filesystem is
      // checked means a future Next.js route handler accidentally created under
      // `app/api/` can never silently shadow a real backend endpoint — the kind
      // of bug that presents as "the endpoint returns 404 in production only".
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: `${API_ORIGIN}/api/:path*`,
        },
      ],
      afterFiles: [],
      fallback: [],
    };
  },

  images: {
    // Profile pictures come from Google, which is the only sign-in provider
    // (ADR 013) and serves avatars from a numbered `lh*` host. Nothing else is
    // allowed through the optimiser: an open image proxy is a way to make this
    // deployment fetch arbitrary URLs on someone's behalf.
    remotePatterns: [
      { protocol: "https", hostname: "**.googleusercontent.com", pathname: "/**" },
    ],
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy() },
          // This app renders user-uploaded PDFs. Clickjacking and MIME sniffing
          // are the two cheapest attacks against that and the two cheapest to
          // shut off.
          //
          // `X-Frame-Options` is kept alongside `frame-ancestors` rather than
          // replaced by it: the CSP directive is the one browsers honour, and
          // this is the fallback for anything that does not.
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
