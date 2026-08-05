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
          // This app renders user-uploaded PDFs. Clickjacking and MIME sniffing
          // are the two cheapest attacks against that and the two cheapest to
          // shut off.
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
