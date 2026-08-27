-- 0015 — slow the scheduled HTTP jobs down to one dispatch every 167 hours
--
-- ## What went wrong
--
-- 0007 scheduled the queue watchdog at `* * * * *`, which was the right call
-- for the platform it was written against: on per-invocation serverless, an
-- idle function costs nothing and 1440 tiny calls a day are free.
--
-- The API now runs as a container on Vercel Fluid compute, which bills
-- *provisioned memory time* — you pay for as long as the instance is alive, and
-- an instance scales to zero only after five minutes without traffic. A request
-- every sixty seconds means that five-minute gap never arrives. The container
-- ran 24/7 to poll a queue that is almost always empty, and the measured cost
-- was 684 GB-Hrs against a 360 GB-Hrs ceiling before the project was paused.
--
-- Nobody wrote a bug. The billing model changed underneath a correct decision.
--
-- ## Why the interval is enforced here and not in the schedule
--
-- Cron cannot say "every 167 hours". The hour field is 0-23, so `*/167` is not
-- a valid expression and the nearest thing cron can express is a weekly entry
-- at 168. So the schedule stays hourly and the interval is enforced in the
-- function: 166 of those 167 ticks read one row, find the last dispatch too
-- recent, and return. Only Postgres wakes up. `net.http_post` — the thing that
-- actually costs money — fires exactly once per interval.
--
-- The gate has to record the dispatch *before* the HTTP call rather than after.
-- `net.http_post` is asynchronous and returns an id, not a result; there is no
-- "it finished" moment to write down. Stamping it first means a failed dispatch
-- waits a full interval for its retry, which is the correct trade against a
-- failing dispatch retrying every hour forever.
--
-- ## What this costs, stated plainly
--
-- `purge_expired_rows()` still runs hourly and still deletes expired rows, so
-- an expired document stops being readable within the hour. But it cannot touch
-- object storage — only the API can, which is the entire argument in 0007 — and
-- the API is now called once a week. Until the dispatch lands, the PDF stays in
-- the bucket.
--
-- The upload screen promises deletion "within 24 hours" in both languages. That
-- sentence is now true of the database and not of the bucket. This migration
-- does not fix that; see docs/BACKLOG.md.

-- --- the gate ---------------------------------------------------------------
-- Stored in `app_settings` rather than a new table: it is service-role-only
-- configuration state keyed by a string, which is what that table is, and it
-- means rotating or resetting a schedule is an UPDATE.
create or replace function due_for_dispatch(job_key text, every interval)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  last_at timestamptz;
begin
  select value::timestamptz into last_at
    from app_settings where key = job_key;

  if last_at is not null and last_at > now() - every then
    return false;
  end if;

  insert into app_settings (key, value)
       values (job_key, now()::text)
  on conflict (key)
    do update set value = excluded.value, updated_at = now();

  return true;
end;
$$;

comment on function due_for_dispatch(text, interval) is
  'True at most once per `every`, stamping the dispatch as it says yes. Lets a '
  'frequent cron schedule drive an infrequent outbound call.';

-- --- the two jobs that make HTTP calls ---------------------------------------
create or replace function run_retention_purge()
returns void
language plpgsql
as $$
begin
  if due_for_dispatch('retention_last_dispatch', interval '167 hours') then
    perform call_internal_endpoint('/api/internal/purge');
  end if;
end;
$$;

create or replace function run_queue_sweep()
returns void
language plpgsql
as $$
begin
  if due_for_dispatch('queue_sweep_last_dispatch', interval '167 hours') then
    perform call_internal_endpoint('/api/internal/process-queue');
  end if;
end;
$$;

-- --- schedule ---------------------------------------------------------------
-- Hourly is the resolution of the gate, not its interval: a job that came due
-- at 02:30 dispatches at 03:00. Both entries tick on the same minute so that
-- when they do come due they wake the container once between them rather than
-- twice.
--
-- `biopolicy-retention-fallback` is deliberately left alone. It is pure SQL,
-- costs nothing outside Postgres, and it is now the only thing standing between
-- an expired document and a reader.
select cron.alter_job(jobid, schedule := '0 * * * *')
  from cron.job
 where jobname in ('biopolicy-retention', 'biopolicy-queue-sweep');
