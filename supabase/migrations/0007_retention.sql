-- 0007 — retention and scheduled jobs
--
-- The 24-hour deletion promise is printed on the upload screen in two
-- languages. That makes it a commitment, not a backlog item.
--
-- ## Why the purge goes through the API rather than deleting rows here
--
-- The obvious implementation is `delete from documents where expires_at < now()`
-- and let `on delete cascade` take the chunks. That correctly removes the
-- database side — and leaves the actual PDF sitting in object storage. Deleting
-- a row from `storage.objects` does not reliably remove the underlying file;
-- the file is removed by the Storage API, which owns the bucket backend.
--
-- A purge that deletes every trace except the document itself would be the
-- worst possible outcome: the audit table would record a successful purge, the
-- tests would pass, and the user's policy PDF would still be on disk.
--
-- So Postgres calls our own endpoint, which deletes the storage object first
-- and the rows second, and writes the audit entry only when both succeeded.

-- --- configuration for scheduled jobs ---------------------------------------
-- RLS enabled with no policy: service-role access only. The purge secret lives
-- here rather than in the cron command text so that rotating it is an UPDATE
-- rather than a migration.
create table app_settings (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);

alter table app_settings enable row level security;

comment on table app_settings is
  'Service-role only. Populate api_base_url and purge_job_secret before the '
  'scheduled jobs will do anything. See docs/RUNBOOK.md.';

-- --- the callable job -------------------------------------------------------
create or replace function call_internal_endpoint(path text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  base   text;
  secret text;
begin
  select value into base   from app_settings where key = 'api_base_url';
  select value into secret from app_settings where key = 'purge_job_secret';

  if base is null or secret is null then
    -- Deliberately a warning, not an exception. Migrations must apply cleanly
    -- to a project that has not been configured yet; the job simply does
    -- nothing until it is. A failing cron job every minute would bury the real
    -- signal in noise.
    raise warning
      'app_settings is missing api_base_url or purge_job_secret; skipping %', path;
    return;
  end if;

  perform net.http_post(
    url     := base || path,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Job-Secret', secret
    ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 30000
  );
end;
$$;

create or replace function run_retention_purge() returns void
language sql as $$ select call_internal_endpoint('/api/internal/purge'); $$;

create or replace function run_queue_sweep() returns void
language sql as $$ select call_internal_endpoint('/api/internal/process-queue'); $$;

-- --- last-resort database-side sweep ----------------------------------------
-- If the API is down for longer than the retention window, the promise must
-- still hold for the data we control. This removes rows and embeddings; the
-- storage object is then orphaned and is reconciled by the API's own sweep.
-- Orphaned-but-unreferenced beats retained-and-queryable.
create or replace function purge_expired_rows()
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  purged int := 0;
begin
  with expired as (
    delete from documents
    where expires_at < now() and not is_sample
    returning id, user_id
  )
  insert into retention_audit (document_id, user_id, storage_deleted)
  select id, user_id, false from expired;

  get diagnostics purged = row_count;
  return purged;
end;
$$;

-- --- schedule ---------------------------------------------------------------
-- Retention every 15 minutes; the queue watchdog every minute. The watchdog is
-- only a safety net — the fast path is an in-process task fired by
-- POST /documents, so this normally finds nothing to do.
select cron.schedule('biopolicy-retention', '*/15 * * * *', 'select run_retention_purge()');
select cron.schedule('biopolicy-queue-sweep', '* * * * *', 'select run_queue_sweep()');

-- Belt and braces: an hour after the API-driven purge should have run, sweep
-- anything still expired straight out of the database.
select cron.schedule('biopolicy-retention-fallback', '7 * * * *', 'select purge_expired_rows()');
