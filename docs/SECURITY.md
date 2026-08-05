# Security

What this system is trying to protect, what it deliberately does not, and what a
review of it actually checked.

This is a public demo with a real bill attached. That shapes the whole model:
the asset worth protecting is not a database of valuable records — it is
**other people's uploaded documents**, and **the money**.

## What an attacker would want

| Goal | What stands in the way |
|---|---|
| Read another visitor's uploaded policy | Every query carries an ownership clause in SQL; signed URLs are 30 minutes and per-object |
| Read another visitor's conversations | Same: owner-scoped in SQL, 404 rather than 403 |
| Spend the demo's budget | Per-account daily quota, then a global breaker, then the provider console limit |
| Get the unlimited allowance | A five-clause check against the account row, not the token |
| Make the database work for free | Public aggregates are cached; everything else needs a session |

## The two decisions that carry the most weight

**Ownership is enforced in SQL, not by RLS.** The API holds a service-role key
and bypasses every policy, so a query that forgot its `user_id` clause would
read anyone's data and no policy would stop it. RLS is still enabled on every
table — it is the second line, for anything that ever reaches the database
without going through this code — but it is not the line being relied on.

**Privilege is decided from the account row, not the token.** The unlimited
allowance is matched on an email address, and an address in a JWT is only as
trustworthy as the provider that issued it. `api/accounts.py` reads
`auth.users` and requires a non-empty allowlist, a usable account, a confirmed
address, and the `google` provider. There is a test per clause, each written as
the way somebody who does not own the address would otherwise get in
([ADR 013](./adr/013-google-only-sign-in.md)).

## What was checked, and how

Reviewed before making the repository public. Each of these was checked
mechanically across the whole codebase rather than by reading the files that
seemed relevant:

- **Ownership clauses.** Every SQL statement touching an owned table, and every
  route taking a user-supplied id. Twelve statements run without an ownership
  clause; all twelve are internal pipeline or retention calls whose id was
  already checked upstream, and each was read individually to confirm it.
- **Injection.** No SQL is built by string interpolation anywhere. Every query
  is parameterised.
- **Secrets in tracked files.** Scanned for provider key shapes, JWTs, database
  URLs with credentials, and personal email addresses. One hit, and it is the
  literal `postgresql://user:password@host:port/database` inside an error
  message explaining the expected format.
- **Log leakage.** No log line carries a question, an answer, a document's
  content, or an email address. Request ids are what tie a report to a trace.
- **Error leakage.** No exception text reaches a client. Unhandled exceptions
  become a generic 500 with a request id; the traceback goes to the server log
  under the same id.
- **Spending paths.** Every route that calls a provider sits behind
  authentication, the global breaker, and a quota check — in that order, before
  the response stream opens.
- **Storage paths.** `uploads/{user_id}/{document_id}.pdf`. No user-controlled
  text in the path, so no traversal sequence can be in it.

## Known and accepted

Stated because a threat model with no accepted risks in it has not been written
honestly.

- **A quota is per account, and accounts are free.** Google raises the cost of
  making one well above an anonymous session, which is why sign-in changed
  ([ADR 013](./adr/013-google-only-sign-in.md)), but it does not make it
  impossible. The global budget breaker is what actually bounds the bill; the
  per-account quota is what stops one ordinary visitor from consuming the demo.
- **The client supplies its own conversation history.** A crafted history can
  steer the model's answer. The blast radius is the sender's own answer — they
  already control the question — and it is bounded by the same daily quota.
  Validating history against stored messages would cost a query per turn to
  prevent somebody from misleading themselves.
- **Cost accounting undercounts.** Google's models were never price-verified,
  so their calls are recorded with tokens and a cost of zero
  (`api/pricing.py` refuses to invent a price). The breaker therefore trips
  later than the true spend would suggest. The provider console's own limit is
  the outer guard and is not optional because this exists.
- **Uploaded PDFs are parsed, not sandboxed.** The parsing stack is pure Python
  wheels with no system binaries (ADR 002), which removes a large class of
  native-code exposure, but a malicious PDF is still processed in the API's own
  process. Page and size caps bound the work; nothing isolates it.
- **The evaluation fixtures live in the same database as the demo.** They are
  marked `is_sample = false` so they never appear in the public picker, and they
  are owned by the seed account. A bug in the samples query would surface a
  deliberately self-contradicting policy to a visitor with no explanation.

## Reporting

This is a portfolio project rather than a service. If you find something,
opening an issue on the repository is the right channel; there is no bounty and
no on-call.
