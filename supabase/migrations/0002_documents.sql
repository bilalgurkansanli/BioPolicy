-- 0002 — documents
--
-- This table is also the ingestion queue. See docs/adr/007: a scale-to-zero
-- container can be reclaimed the moment it writes its 202, so an in-process
-- background task is not a durable home for a multi-minute pipeline. The row is
-- the durable record; `claimed_at` and `attempts` are what make recovery
-- possible.

create table documents (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,

  filename       text not null,
  storage_path   text not null,
  byte_size      bigint not null,
  page_count     int,
  detected_lang  text,                      -- ISO 639-1
  source_type    text,                      -- 'native' | 'scanned' | 'mixed'

  status         text not null default 'queued',
  error_message  text,                      -- user-safe text only, never a traceback

  -- --- queue bookkeeping (ADR 007) ---------------------------------------
  -- When a worker claimed this row. A claim older than the stale threshold is
  -- reclaimable: that single rule is the entire crash-recovery mechanism.
  claimed_at     timestamptz,
  attempts       int not null default 0,

  is_sample      boolean not null default false,
  created_at     timestamptz not null default now(),

  -- The 24-hour promise is printed on the upload screen in two languages.
  -- 0007 enforces it. Samples are exempt and carry a far-future expiry.
  expires_at     timestamptz not null default now() + interval '24 hours',

  constraint documents_status_valid check (
    status in ('queued', 'parsing', 'ocr', 'chunking', 'embedding', 'ready', 'failed')
  ),
  constraint documents_source_type_valid check (
    source_type is null or source_type in ('native', 'scanned', 'mixed')
  ),
  constraint documents_byte_size_positive check (byte_size > 0),
  -- A sample that expires would delete itself and break the public demo.
  constraint documents_samples_do_not_expire check (
    not is_sample or expires_at > now() + interval '365 days'
  )
);

comment on column documents.error_message is
  'User-facing text only. Never write a stack trace here; it reaches the client.';

-- The queue sweep's access pattern: claimable rows, oldest first.
create index documents_queue_idx
  on documents (status, claimed_at nulls first, created_at)
  where status <> 'ready' and status <> 'failed';

-- The retention job's access pattern.
create index documents_expiry_idx on documents (expires_at) where not is_sample;

create index documents_user_idx on documents (user_id, created_at desc);
