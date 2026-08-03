-- 0004 — conversations, messages, usage
--
-- `messages` stores what the anti-hallucination layer decided, not just what it
-- said. `groundedness_score`, `refused` and `citations` are what make the
-- evaluation report reproducible from production data rather than only from a
-- test harness.

create table conversations (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  document_id    uuid not null references documents(id) on delete cascade,
  title          text,
  -- Rolling summary of turns older than the verbatim window. Bounded on
  -- purpose: stale context is a leading cause of confident wrong answers in
  -- chat RAG, so old turns are compressed rather than carried.
  summary        text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index conversations_user_idx on conversations (user_id, updated_at desc);
create index conversations_document_idx on conversations (document_id);

create table messages (
  id                 uuid primary key default gen_random_uuid(),
  conversation_id    uuid not null references conversations(id) on delete cascade,
  user_id            uuid not null references auth.users(id) on delete cascade,

  role               text not null,          -- 'user' | 'assistant'
  content            text not null,

  -- --- anti-hallucination outcome (assistant messages only) --------------
  -- Citations that SURVIVED binding. A citation dropped for naming a chunk that
  -- was never retrieved, or quoting text that is not in its chunk, never
  -- reaches this column.
  citations          jsonb not null default '[]'::jsonb,
  groundedness_score real,
  refused            boolean not null default false,
  -- True when an answer was suppressed because every citation failed binding.
  -- This is a caught hallucination, and it is counted rather than hidden.
  suppressed         boolean not null default false,
  -- Which prompt produced this. Prompts are code; a metric without a prompt
  -- version attached is not reproducible.
  prompt_version     text,
  model              text,
  retrieved_chunk_ids uuid[] not null default '{}',

  created_at         timestamptz not null default now(),

  constraint messages_role_valid check (role in ('user', 'assistant')),
  constraint messages_groundedness_range check (
    groundedness_score is null or (groundedness_score >= 0 and groundedness_score <= 1)
  )
);

create index messages_conversation_idx on messages (conversation_id, created_at);

create table usage_events (
  id             bigserial primary key,
  user_id        uuid references auth.users(id) on delete set null,
  -- Kept when the user is deleted: the budget breaker must still see the spend.
  -- This is why the FK above is `set null` rather than `cascade`.
  operation      text not null,     -- 'embed' | 'answer' | 'verify' | 'ocr' | 'rewrite'
  model          text not null,
  input_tokens   int not null default 0,
  output_tokens  int not null default 0,
  cost_usd       numeric(12, 6) not null default 0,
  created_at     timestamptz not null default now()
);

comment on table usage_events is
  'Written AFTER every provider call. The global circuit breaker sums cost_usd '
  'over this table. Application accounting can be wrong — the provider console '
  'spend limit is the outer guard and is never disabled because this exists.';

create index usage_events_created_idx on usage_events (created_at desc);
create index usage_events_user_day_idx on usage_events (user_id, created_at desc);

-- --- retention audit --------------------------------------------------------
-- Every purge is logged. An untested, unlogged retention promise is a
-- liability, not a feature.
create table retention_audit (
  id                 bigserial primary key,
  document_id        uuid not null,
  user_id            uuid,
  chunks_deleted     int not null default 0,
  storage_deleted    boolean not null default false,
  purged_at          timestamptz not null default now()
);

create index retention_audit_purged_idx on retention_audit (purged_at desc);
