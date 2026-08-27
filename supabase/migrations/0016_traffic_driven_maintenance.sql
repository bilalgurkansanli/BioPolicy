-- 0016 — stop dispatching from Postgres; let traffic drive the sweeps
--
-- 0015 cut the two outbound jobs from one call a minute to one call every 167
-- hours, which fixed the bill. This removes them, which fixes the shape.
--
-- ## The reasoning 0015 only half-followed
--
-- The cost on Fluid compute is not the work, it is the *waking*. A container is
-- billed for its whole lifetime and only scales down after five minutes without
-- traffic, so any scheduled call — however rare — buys a five-minute minimum of
-- provisioned memory to do a few milliseconds of work. 0015 made that rare.
-- Rare is not the same as free, and rare is also worse at the job: a stranded
-- document waited a week.
--
-- A request from a real user has already paid for the container. It is awake,
-- the five-minute tail is already running, and a sweep inside that window is
-- close to free. So the trigger moves from a clock to traffic. See
-- `api/maintenance.py`, which holds the full argument.
--
-- ## What still runs on a timer, and why that is not a contradiction
--
-- `biopolicy-retention-fallback` stays exactly as it is. It is pure SQL inside
-- Postgres — no `net.http_post`, no container, no Vercel — so it costs nothing
-- on the meter that caused all of this. It is also the half of the 24-hour
-- promise that must not depend on anyone visiting the site: it deletes expired
-- rows every hour, so nothing stays readable past its window even if the site
-- sees no traffic for a month.
--
-- What it cannot do is delete the storage object, which is the entire argument
-- in 0007. That half now waits for a visitor. Rows expire on the clock, files
-- are collected on traffic.
--
-- ## The functions stay, ungated
--
-- `run_retention_purge()` and `run_queue_sweep()` keep their 0007 bodies rather
-- than being dropped. Nothing calls them on a schedule any more, but they are
-- the manual escape hatch the runbook reaches for — "purge right now" — and a
-- gate that silently refuses is the wrong behaviour for a hand-run command.
-- `due_for_dispatch` survives too: the API now uses it as its own hourly gate,
-- which is where the interval belongs, because that is where the trigger is.

-- --- unschedule the outbound jobs -------------------------------------------
select cron.unschedule(jobid)
  from cron.job
 where jobname in ('biopolicy-retention', 'biopolicy-queue-sweep');

-- --- and give the manual commands their teeth back ---------------------------
create or replace function run_retention_purge() returns void
language sql as $$ select call_internal_endpoint('/api/internal/purge'); $$;

create or replace function run_queue_sweep() returns void
language sql as $$ select call_internal_endpoint('/api/internal/process-queue'); $$;

comment on function run_retention_purge() is
  'Manual. Nothing schedules this since 0016 — the API sweeps on traffic.';
comment on function run_queue_sweep() is
  'Manual. Nothing schedules this since 0016 — the API sweeps on traffic.';

-- The 0015 dispatch stamps belonged to the schedule that is now gone. Leaving
-- them would mean a future reader finds two keys that nothing reads.
delete from app_settings
 where key in ('retention_last_dispatch', 'queue_sweep_last_dispatch');
