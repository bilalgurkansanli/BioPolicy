-- 0003 — chunks
--
-- The embedding dimension is 1536, NOT the model's native 3072.
--
-- pgvector will happily store 3072 dimensions and then silently refuse to build
-- an HNSW index over them, because HNSW tops out at 2000. The result is not an
-- error — it is every query falling back to a sequential scan across every
-- chunk in the table. A performance cliff with no log line.
--
-- gemini-embedding-001 is Matryoshka-trained, so requesting 1536 via
-- `output_dimensionality` is a designed-for truncation rather than lossy
-- mangling. This number must stay in step with api/constants.py::EMBEDDING_DIM;
-- SQL cannot import it, so the two are kept in sync by hand and guarded by a
-- unit test asserting the Python constant stays under the index ceiling.

create table chunks (
  id             uuid primary key default gen_random_uuid(),
  document_id    uuid not null references documents(id) on delete cascade,

  -- Denormalised from documents so RLS can be enforced on this table without a
  -- join. A leak here leaks document *content*, not just metadata.
  user_id        uuid not null references auth.users(id) on delete cascade,

  ordinal        int not null,
  content        text not null,
  content_type   text not null default 'text',   -- 'text' | 'table'

  page_start     int,
  page_end       int,
  bbox           jsonb,          -- {x0, top, x1, bottom}, top-left origin, PDF points
  section_path   text,           -- e.g. 'Madde 4 > 4.7'
  token_count    int,

  embedding      vector(1536) not null,

  created_at     timestamptz not null default now(),

  constraint chunks_content_type_valid check (content_type in ('text', 'table')),
  constraint chunks_pages_ordered check (
    page_start is null or page_end is null or page_end >= page_start
  ),
  constraint chunks_unique_ordinal unique (document_id, ordinal)
);

comment on column chunks.bbox is
  'Top-left origin, PDF points, page-relative. pdfium''s native bottom-left '
  'coordinates are flipped once at the parser boundary — see api/ingest/types.py.';

-- --- full-text search -------------------------------------------------------
--
-- The `turkish` configuration ships with Postgres, but this is verified at
-- migration time rather than assumed. If it is absent we fall back to `simple`
-- and say so loudly, because a silently-broken FTS column would degrade Turkish
-- retrieval with no error anywhere — the eval would report the damage without
-- ever explaining it.
--
-- The config is baked in as a literal because `to_tsvector(regconfig, text)` is
-- only immutable, and therefore only usable in a generated column, when the
-- configuration is fixed rather than resolved from the session.
do $$
declare
  tr_config text;
begin
  if exists (select 1 from pg_ts_config where cfgname = 'turkish') then
    tr_config := 'turkish';
  else
    tr_config := 'simple';
    raise warning
      'Postgres has no ''turkish'' text-search configuration; falling back to '
      '''simple''. Turkish keyword retrieval will not stem. Record this in an ADR.';
  end if;

  execute format(
    'alter table chunks add column fts_tr tsvector '
    'generated always as (to_tsvector(%L::regconfig, content)) stored',
    tr_config
  );
end
$$;

alter table chunks
  add column fts_en tsvector
  generated always as (to_tsvector('english'::regconfig, content)) stored;

-- --- indexes ----------------------------------------------------------------

-- WHY cosine and not L2: the embeddings are normalised, so cosine distance is
-- the metric the model was trained against. Mixing metrics between index and
-- query silently degrades ranking rather than failing.
create index chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);

create index chunks_fts_tr_idx on chunks using gin (fts_tr);
create index chunks_fts_en_idx on chunks using gin (fts_en);

-- Every retrieval query is scoped to one document. This index is what keeps the
-- vector search from ranging across every user's chunks.
create index chunks_document_idx on chunks (document_id, ordinal);
create index chunks_user_idx on chunks (user_id);
