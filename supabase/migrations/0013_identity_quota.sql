-- A daily allowance that survives deleting the account.
--
-- ## The hole this closes
--
-- Every limit in `api/safety/quota.py` was counted per `auth.users.id`, and both
-- sources of that count disappear when an account does:
--
--   * `usage_events.user_id` is `on delete set null` (migration 0004), so the
--     spend stays on the books for the budget breaker but stops being anybody's.
--   * `documents` is `on delete cascade` (migration 0002), so the rows go.
--
-- Sign in with the same Google account afterwards and Supabase mints a *new*
-- user id, both counters read zero, and the daily allowance is fresh. Measured
-- on the development project before this migration: 28 of 152 `usage_events`
-- rows were already ownerless, and all three of that day's answers sat under a
-- null user with a live account holding a full allowance.
--
-- ## Why not simply stop offering account deletion
--
-- Because the privacy notice promises it in two languages, because erasure is a
-- right under KVKK art. 7 and GDPR art. 17, and because it would not even work:
-- a second Google account resets the allowance without deleting anything. The
-- limit has to follow the *identity*, not the row.
--
-- ## What is stored, and what is deliberately not
--
-- `subject` is an HMAC-SHA256 of Google's `sub` — the provider's own stable id
-- for an account, from `auth.identities.provider_id` — keyed with
-- `QUOTA_SUBJECT_PEPPER`. No address, no name, no token. Without the pepper the
-- column is not reversible, and with it the only question it can answer is "has
-- this identity already asked today", which is the question it exists for.
--
-- Rows are purged after 7 days by the same sweep that purges documents. A row
-- for a past day has no function in the limit; the week is what makes an account
-- being cycled daily visible while it is happening.
create table identity_quota (
  -- hex HMAC-SHA256, so 64 characters. Not `uuid`: it is a digest, and typing it
  -- as one would invite somebody to read it as an id that means something.
  subject     text        not null,
  day         date        not null,
  questions   integer     not null default 0,
  documents   integer     not null default 0,
  updated_at  timestamptz not null default now(),
  primary key (subject, day)
);

comment on table identity_quota is
  'Daily allowance counted per Google identity rather than per account row, so '
  'that deleting an account does not reset it. Holds a keyed digest and two '
  'integers — never an address. Purged after 7 days.';

comment on column identity_quota.subject is
  'HMAC-SHA256(QUOTA_SUBJECT_PEPPER, google sub). Irreversible without the pepper.';

-- The purge sweep scans by age.
create index identity_quota_day_idx on identity_quota (day);

-- Enabled with no policy at all, which is the deny-all this table wants: nothing
-- here belongs to a signed-in user in the sense RLS expresses, and the API holds
-- the service-role key. A reader who reaches this table through PostgREST with
-- an anon or authenticated token sees nothing.
alter table identity_quota enable row level security;
