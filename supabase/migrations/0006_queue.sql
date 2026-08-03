-- 0006 — the ingestion queue claim function (ADR 007)
--
-- `documents` is the queue. This function is the only sanctioned way to take
-- work off it.
--
-- The important clause is `for update skip locked`. It lets the fast-path task
-- fired by POST /documents and the pg_cron watchdog race harmlessly: whichever
-- transaction reaches the row first locks it, and the other skips straight past
-- rather than blocking or double-processing.

create or replace function claim_next_document(
  stale_after  interval default '5 minutes',
  max_attempts int default 3
)
returns documents
language plpgsql
security definer
set search_path = public
as $$
declare
  claimed documents;
begin
  select * into claimed
  from documents
  where
    -- Fresh work.
    (status = 'queued')
    -- Or work stranded by an instance that was reclaimed mid-pipeline. This
    -- single clause is the entire crash-recovery mechanism: no heartbeats, no
    -- separate watchdog table.
    or (
      status in ('parsing', 'ocr', 'chunking', 'embedding')
      and claimed_at is not null
      and claimed_at < now() - stale_after
    )
  and attempts < max_attempts
  order by claimed_at nulls first, created_at
  limit 1
  for update skip locked;

  if not found then
    return null;
  end if;

  update documents
  set claimed_at = now(),
      attempts   = attempts + 1,
      status     = 'parsing'
  where id = claimed.id
  returning * into claimed;

  return claimed;
end;
$$;

comment on function claim_next_document is
  'Atomically claims one document for ingestion. Safe to call concurrently.';

-- Documents that have exhausted their retries are terminal failures. Without
-- this, a PDF that reliably crashes the parser becomes an infinite billing
-- loop: claimed, crashed, reclaimed as stale, forever.
create or replace function fail_exhausted_documents(max_attempts int default 3)
returns int
language sql
as $$
  with exhausted as (
    update documents
    set status = 'failed',
        error_message = coalesce(
          error_message,
          'We could not process this document after several attempts. '
          'It may be corrupted or password-protected.'
        )
    where status in ('parsing', 'ocr', 'chunking', 'embedding')
      and attempts >= max_attempts
      and claimed_at < now() - interval '5 minutes'
    returning 1
  )
  select count(*)::int from exhausted;
$$;
