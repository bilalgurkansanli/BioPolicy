-- 0005 — row level security
--
-- READ THIS BEFORE TRUSTING IT.
--
-- The API holds a service-role key and therefore **bypasses every policy in
-- this file**. RLS here is defence in depth: it protects against a leaked anon
-- key, a misconfigured PostgREST call, and a future direct-from-browser query.
-- It does NOT protect against a missing WHERE clause in our own code.
--
-- Every query in api/retrieval/store.py must scope by user_id itself. Reading
-- "RLS is enabled" as "we are safe" is the mistake this comment exists to
-- prevent.

alter table documents       enable row level security;
alter table chunks          enable row level security;
alter table conversations   enable row level security;
alter table messages        enable row level security;
alter table usage_events    enable row level security;
alter table retention_audit enable row level security;

-- --- documents --------------------------------------------------------------
-- Samples are readable by anyone, including anonymous visitors: the public demo
-- is queryable without an upload. Everything else is owner-only.
create policy documents_select_own_or_sample on documents
  for select using (auth.uid() = user_id or is_sample);

create policy documents_insert_own on documents
  for insert with check (auth.uid() = user_id);

create policy documents_update_own on documents
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- A user may delete their own document at any time; the API exposes this as an
-- immediate purge rather than making them wait out the 24 hours.
create policy documents_delete_own on documents
  for delete using (auth.uid() = user_id and not is_sample);

-- --- chunks -----------------------------------------------------------------
-- A leak here leaks document content. Chunks of a sample document are readable
-- by anyone, mirroring the documents policy, because the demo has to work.
create policy chunks_select_own_or_sample on chunks
  for select using (
    auth.uid() = user_id
    or exists (select 1 from documents d where d.id = chunks.document_id and d.is_sample)
  );

-- Chunks are written only by the ingestion pipeline, which uses the service
-- role. No insert/update policy for regular users is intentional.

-- --- conversations and messages --------------------------------------------
create policy conversations_all_own on conversations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy messages_all_own on messages
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- --- usage ------------------------------------------------------------------
-- A user may see their own spend, via GET /api/usage. Nobody may write it from
-- the client: usage is recorded server-side after the provider call, and a
-- client-writable usage table would make the budget breaker trivially
-- defeatable.
create policy usage_select_own on usage_events
  for select using (auth.uid() = user_id);

-- --- retention audit --------------------------------------------------------
-- Service-role only. Deliberately no policy: with RLS enabled and no policy,
-- every non-service-role query returns zero rows.
