-- Embeddings move from Gemini to Voyage, and the column has to move with them.
--
-- ## Why the width changes
--
-- `voyage-4-lite` offers 256, 512, 1024 and 2048 dimensions. 2048 is above
-- pgvector's HNSW ceiling of 2000, so 1024 is the largest usable one. The old
-- column was `vector(1536)`, a truncation of Gemini's native 3072 chosen under
-- the same ceiling.
--
-- 1024 is also a width `gemini-embedding-001` can produce, which is deliberate:
-- the fallback embedder still fits the column, so switching providers cannot
-- silently write vectors of the wrong shape.
--
-- ## Why every existing vector is deleted rather than converted
--
-- There is no conversion. A vector is a point in a space defined by the model
-- that produced it; the same clause embedded by two models lands in two
-- unrelated spaces, and the distance between them means nothing. Keeping the
-- old rows and querying them with new query vectors would not error — it would
-- return confident, arbitrary results, which is the worst possible failure for
-- a retrieval system and exactly the kind this project exists to avoid.
--
-- So the chunks go, and the documents that own them are put back in the queue.
-- The pipeline re-parses, re-chunks and re-embeds them, which is the same work
-- a first ingest does (ADR 007 makes ingestion idempotent for this reason).
--
-- Uploaded documents are NOT re-queued: they expire within 24 hours anyway, and
-- their owners are better served by a document that has plainly gone than by
-- one that silently answers from nothing. Samples are re-seeded by
-- `python -m api.scripts.seed_samples`.

-- The index depends on the column type, so it goes first.
drop index if exists chunks_embedding_idx;

delete from chunks;

alter table chunks
  alter column embedding type vector(1024);

-- Rebuilt with the same parameters as migration 0003. Cosine, because the
-- vectors are unit-length and cosine is what the retriever's `<=>` operator
-- uses; the two must agree or every distance is computed under one metric and
-- interpreted under another.
create index chunks_embedding_idx
    on chunks using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- Sample documents rebuild from the seeder; anything else a user still owns is
-- marked so the interface can say what happened rather than showing an empty
-- document that answers nothing.
update documents
   set status = 'queued', error_message = null, attempts = 0
 where is_sample;

comment on column chunks.embedding is
  'voyage-4-lite at 1024 dimensions (ADR 016). Width is bounded by pgvector''s HNSW ceiling of 2000, not by the model.';
