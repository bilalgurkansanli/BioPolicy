# ADR 006 — Two Vercel projects behind one origin, joined by a rewrite

- **Status:** accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

The frontend is a Next.js app. The backend is a Python container image. Both
deploy to Vercel, and the spec requires them to appear at a single origin —
`biopolicy.bilalgurkansanli.com` — with the API under `/api/*`.

These are two different build systems producing two different artifacts from one
repository. They also have genuinely different lifecycles: a copy change on the
landing page should not rebuild and redeploy a container that takes minutes to
push.

## Decision

Two Vercel projects from the same repository:

- **web** — root directory `web/`, standard Next.js build, owns the custom
  domain.
- **api** — root directory `.`, built from `Dockerfile.vercel`, reachable at its
  own `*.vercel.app` hostname.

`web/next.config.ts` rewrites `/api/:path*` to the API deployment. The browser
therefore only ever talks to one origin.

## Consequences

**Bought:** the browser makes same-origin requests, so there is no CORS
preflight on any call, no third-party cookie question for Supabase auth, and the
`Authorization` header passes through untouched. The two halves deploy
independently. `CORS_ALLOW_ORIGINS` stays empty in production and exists only
for split-origin local development.

**Cost:** every API call takes an extra network hop through the Next.js edge.
That is a real latency tax and it lands hardest on the SSE chat stream, which is
the most latency-sensitive path in the product. **This needs measuring in Phase
3 rather than assuming** — if the rewrite buffers the stream instead of passing
it through, tokens will arrive in bursts and the streaming UI becomes
pointless. The fallback if that happens is to point the browser directly at the
API hostname for `/api/chat` only, and pay the CORS cost on that one route.

Also: two projects means two sets of environment variables to keep in sync, and
a preview deployment of one half can be paired with a stale other half.

**Revisit if:** streaming through the rewrite proves lossy or buffered.

## Alternatives considered

**One Vercel project serving both.** Fewer moving parts and no extra hop.
Rejected: a single project has one build pipeline, and Next.js plus a Python
container image are not one build pipeline. It also couples deploy cadence — a
frontend typo fix would redeploy the API.

**Backend on a separate host (Fly.io, Render) with the frontend on Vercel.**
Removes the container-on-Vercel question entirely and gives a long-running
process, which would incidentally solve the background-job problem in ADR 007
for free. Rejected because the container deployment is confirmed working and
keeping one platform means one dashboard, one set of secrets, one bill, and one
place to look when it breaks. This stays the documented fallback.

**API as a subdomain, e.g. `api.biopolicy.…`, with CORS.** Rejected: it buys
nothing over the rewrite and adds a preflight to every request plus a
cross-origin credential story for auth.
