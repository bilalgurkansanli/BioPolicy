# ADR 013 — Google-only sign-in, and one allowlisted account

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 7
- **Supersedes:** [ADR 012](./012-anonymous-accounts.md)

## Context

ADR 012 chose anonymous accounts, and named its own weakness: an anonymous
account is free to create, so per-user quotas were a courtesy limit that a
determined visitor resets by clearing site data. That was tolerable while the
allowance was forty questions a day and the real guard was the global budget
breaker.

It stopped being tolerable at **three**. A limit that small is worth evading,
and an identity that costs nothing to mint is not a limit at all — it is a
speed bump with a counter attached.

A second thing changed at the same time: conversations are now saved. A saved
conversation belongs to somebody, and "somebody" cannot be an identity that
vanishes when a browser is cleared.

## Decision

**Google is the only way in.** No anonymous sign-in, no email/password, no
magic link.

One provider is worth more than the sum of its convenience. It gives an identity
that costs a real Google account to create, an email address that Google has
verified, and exactly one authentication path to reason about. Every additional
provider is another way the same address can arrive with a different amount of
proof behind it.

**Browsing stays open.** The samples, the viewer and the evaluation report need
no account. Sign-in is required at the point where it becomes true that somebody
must be counted: asking a question and uploading a document. A portfolio piece
whose whole argument is "watch it refuse correctly" should not put a login form
in front of the watching.

**One account is exempt from the limits**, by email address, configured in the
environment rather than in code — the repository is public and the address is a
personal one.

## How the exemption is decided, and why not from the token

The token carries an `email` claim. It is signed, so it has not been tampered
with, and for identity that is enough: `sub` is the user id and no lookup would
improve it.

It is not enough for *privilege*. An address in a token is only as trustworthy
as the path that put it there, and that path is a dashboard setting away from
changing. So the check reads the account row (`api/accounts.py`) and requires,
all of them:

* the allowlist to be non-empty — an unconfigured deployment grants nothing;
* the account to exist and be usable — not banned, deleted or anonymous;
* the address to be **confirmed** — an unconfirmed address is a claim;
* the provider to be **google** — the clause that keeps a future
  "let's also enable email sign-up" from silently becoming a privilege
  escalation;
* the address to match, case-insensitively.

`api/tests/test_accounts.py` has one test per clause, each written as the way
somebody who does not own the address would otherwise get in.

The exemption is consulted in exactly two places, both inside `QuotaGuard`.
There is no third path that spends money.

## Consequences

**Bought:** a limit that means something, conversations with an owner, and one
authentication path.

**Cost, and it is real:** a visitor without a Google account cannot try the
demo at all, and some people will not sign in to try a stranger's portfolio
project. That is the price of a three-question allowance being enforceable.
Browsing the samples and the evaluation without an account is what keeps the
cost from being total.

**Also cost:** a dependency on Google's consent screen, which for an
unverified OAuth app shows a warning until it is verified. Fine for a demo,
and it would need addressing before this were a product.

**Revisit if:** the allowance ever becomes generous enough that evading it is
not worth the effort, or if the project acquires users who need an account
without Google.

## Alternatives considered

**Keep anonymous sign-in and lower the limit anyway.** Rejected in Context: at
three questions the evasion is one click, and the counter would be measuring
browsers rather than people.

**Anonymous *plus* Google, with different limits.** Two paths to authenticate,
two sets of quota rules, and the allowlist clause above would have to trust an
address arriving down either. More surface, for the benefit of not asking.

**A server-side allowlist keyed on user id instead of email.** Strictly the
safest — no address comparison at all — but the id does not exist until the
account signs in once, so it cannot be configured ahead of time. The provider
and confirmation clauses close the gap that email introduces.
