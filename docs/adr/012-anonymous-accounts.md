# ADR 012 — Anonymous accounts, not sign-up

- **Status:** superseded by [ADR 013](./013-google-only-sign-in.md)
- **Date:** 2026-08-05
- **Phase:** 6

> **Superseded.** The weakness this ADR named — an anonymous account costs
> nothing to create, so per-user quotas are a courtesy — became decisive once
> the allowance dropped to three questions a day and conversations started being
> saved. See [ADR 013](./013-google-only-sign-in.md). The reasoning below is
> kept because the trade it describes is still the right one at a larger
> allowance.

## Context

Uploading needs an identity. Not for the user's benefit — there is nothing to
come back to — but for the system's: quotas are per user, storage paths are
scoped by user id, RLS policies key off `auth.uid()`, and the retention job
deletes by owner. Without an identity, the upload endpoint is an open door onto
a metered API.

The obvious options were email+password, a magic link, and Supabase's anonymous
sign-in.

The thing that decides it is the product's own promise: **everything is deleted
after 24 hours.** A system that deletes your document by tomorrow has no
business holding your email address indefinitely to have done it. Collecting an
identifier that outlives the data it identifies is exactly backwards, and under
KVKK/GDPR it converts a demo with no personal data into one with a lawful-basis
question attached.

The second consideration is smaller but real: an account form is a wall in front
of the thing the visitor came to try. This is a portfolio demo whose whole point
is "watch it refuse correctly" — a signup step before that is a step most
visitors will not take.

## Decision

Sign-in is **anonymous**, via `supabase.auth.signInAnonymously()`, and it happens
**lazily** — on the first authenticated action, not on page load. Browsing the
samples creates nothing; a visitor who never uploads never becomes a row in
`auth.users`.

The resulting JWT is an ordinary Supabase token: same signing key, same audience,
same verification path (`api/auth.py`). Nothing downstream knows or cares that
the user is anonymous, other than the `is_anonymous` claim being carried on
`AuthenticatedUser` for future use.

The Supabase client owns the session and refreshes it. Anonymous sessions expire
like any other, and a hand-rolled fetch holding one token starts returning 401s
an hour into a long visit.

## Consequences

**Bought:** no personal data, no form, no password reset flow, no SMTP. Quotas,
RLS and per-user storage paths all work exactly as they would with real accounts,
because the token is a real token.

**Cost, and it is the honest weakness of this design:** an anonymous account is
free to create, so per-user quotas are trivially reset by clearing site data.
They are a courtesy limit, not a security control. What actually bounds the
spend is the global budget breaker (`api/safety/breaker.py`), which does not care
how many identities the spend arrived under, and behind that the provider
console's own limit. Supabase rate-limits anonymous sign-ins per IP, which raises
the cost of the attack without changing its shape.

**Also bought, unintentionally:** a session that survives a refresh but not a
different browser. There is no "my documents" across devices, which for a
24-hour retention window is a difference nobody will notice.

**Operational prerequisite:** anonymous sign-ins are **off by default** on a
Supabase project. Until they are enabled under *Authentication → Sign In /
Providers*, every upload fails. The interface detects the
`anonymous_provider_disabled` error specifically and names that setting, because
a generic "sign-in failed" would send an operator looking for a bug in code that
is working.

**Revisit if:** the product ever wants documents to persist past a session, or
needs to contact a user about their own document. Both mean a real account, and
both mean the retention promise has changed first.

## Alternatives considered

**Email magic link.** Rejected on the retention argument above, and separately on
operations: Supabase's built-in SMTP is rate-limited to a handful of emails per
hour, so the demo would fail under exactly the traffic that makes it worth having.
A real SMTP provider is another vendor and another credential for a feature the
product does not want.

**Email + password.** Everything wrong with the magic link, plus a password to
store and reset, in service of an account whose data is gone by tomorrow.

**No identity at all — a signed cookie minted by the API.** Tempting, and it
would work for quotas. It means writing our own token issuance and verification
next to a project that already has an auth server doing it, and it leaves RLS
with no `auth.uid()` to key on, so the storage policies would have to be replaced
with application-level checks. More code, in the security-critical direction, to
avoid one dashboard toggle.
