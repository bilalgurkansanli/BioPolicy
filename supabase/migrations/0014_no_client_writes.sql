-- 0014 — take write access away from the browser
--
-- ## What was reachable
--
-- Supabase serves every table in `public` over PostgREST, with the anon key
-- that ships in the frontend bundle. That is by design and the read side was
-- built for it: 0005's select policies are what make a sample document public
-- and everything else owner-only, and they hold.
--
-- The write side was never built for it. 0005 granted `insert`, `update` and
-- `delete` on `documents` to any signed-in user, checked only against
-- `auth.uid() = user_id`. A policy cannot restrict *columns*, so "your own row"
-- meant every column of it, including four that are not the owner's business:
--
--   is_sample     the daily upload count reads `not is_sample` (api/safety/
--                 quota.py) and the retention sweep reads it too (0007, api/
--                 retention.py). Setting it true on your own document takes the
--                 document out of the quota, out of the 24-hour deletion, and
--                 into the sample list every visitor sees.
--   storage_path  GET /documents/{id}/url signs whatever path the row holds,
--                 for any row that is a sample or yours. A row is insertable
--                 and the column is writable, so the endpoint will sign a path
--                 the caller chose.
--   status        'ready' is what makes a document answerable and listable.
--   expires_at    the 24-hour promise, in a column its subject can move.
--
-- None of this needed a leaked key or a bug in our code. It needed the public
-- anon key, a Google sign-in, and one HTTP request.
--
-- ## Why revoking costs nothing
--
-- The browser does not read or write these tables directly. `web/lib/supabase.
-- ts` uses supabase-js for authentication only — there is no `.from(...)` and
-- no `.storage...` call anywhere in `web/` — and every piece of data reaches
-- the interface through the API, which holds the service-role key and bypasses
-- RLS entirely. So this removes an attack surface the application never stood
-- on, and no request the app makes changes at all.
--
-- ## Belt and braces
--
-- Both halves are here on purpose. `revoke` is the one that binds — a missing
-- privilege stops the statement before any policy is consulted — and dropping
-- the policies is what keeps the file honest, so nobody reads 0005 later and
-- concludes writing is intended. Turning the Data API off entirely (Supabase →
-- Settings → API) is worth doing as well; it is a project setting rather than a
-- migration, which is exactly why it should not be the only thing standing
-- between the anon key and this table.

-- --- documents ---------------------------------------------------------------
drop policy if exists documents_insert_own on documents;
drop policy if exists documents_update_own on documents;
drop policy if exists documents_delete_own on documents;

-- Deleting "now" rather than waiting out the retention timer is still offered,
-- and still goes through DELETE /api/documents/{id} — which purges the storage
-- object before the row (api/retention.py). A direct row delete never could:
-- it would have left the PDF in the bucket with nothing pointing at it and
-- nothing to expire it, which is the one state the whole retention module is
-- ordered to prevent.
revoke insert, update, delete on documents from anon, authenticated;

-- --- conversations and messages ----------------------------------------------
-- 0005 wrote these as `for all`, which is the same grant in a shorter form. The
-- API owns every write: titles are derived from the first question, turns are
-- appended as they are answered, and both are read back to rebuild a thread. A
-- client-writable transcript is a transcript that can disagree with the answers
-- it is a record of.
drop policy if exists conversations_all_own on conversations;
drop policy if exists messages_all_own on messages;

create policy conversations_select_own on conversations
  for select using (auth.uid() = user_id);

create policy messages_select_own on messages
  for select using (auth.uid() = user_id);

revoke insert, update, delete on conversations from anon, authenticated;
revoke insert, update, delete on messages from anon, authenticated;

-- --- the rest ----------------------------------------------------------------
-- No policy has ever allowed writing these, so RLS already refuses. Stated
-- anyway: the deny here should not depend on a policy continuing not to exist.
revoke insert, update, delete on chunks from anon, authenticated;
revoke insert, update, delete on usage_events from anon, authenticated;
revoke insert, update, delete on retention_audit from anon, authenticated;

comment on table documents is
  'Written only by the API, which holds the service-role key. 0014 revoked '
  'insert/update/delete from anon and authenticated: a policy cannot restrict '
  'columns, and is_sample, storage_path, status and expires_at are all load '
  'bearing for the quota, the retention promise and the signed viewing URL.';
