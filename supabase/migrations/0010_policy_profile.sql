-- The document read into a fixed schema, cached.
--
-- Typed extraction sweeps the whole document rather than retrieving eight
-- chunks for a question, so it costs several model calls where an answer costs
-- one or two. Recomputing that every time somebody opens a sample document
-- would make the demo's most expensive operation also its most repeated one.
--
-- Cached on the document row rather than in a table of its own, following
-- `0009_injection_findings.sql`: there is exactly one profile per document, it
-- is always read with the document, and nothing queries by its contents. A
-- table would buy a join and a second RLS policy for no lookup.
--
-- Three states, and the interface distinguishes all three:
--
--   null          the profile has not been extracted yet
--   {...}         extracted; `entries` may still be empty
--   entries: []   extracted and the document filled no slots
--
-- Collapsing "not extracted" into "nothing found" is the same error this
-- feature exists to avoid — a slot nobody looked at must never render as a slot
-- the document is silent on.
--
-- Deleted with the document by the existing cascade: this is a column on
-- `documents`, so the 24-hour retention purge and a user's own delete both take
-- it with them without any new code. Nothing in `api/retention.py` changes.
alter table documents
  add column if not exists policy_profile jsonb;

comment on column documents.policy_profile is
  'Typed extraction of this document, cached. null = not extracted yet; an object with entries: [] = extracted and the document filled no slots. Carries its own coverage counters, so a partial sweep is never presented as a complete reading.';
