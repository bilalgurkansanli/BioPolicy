-- Answers, cached per (document, question).
--
-- The demo serves three sample documents to every visitor, and the interface
-- offers each one the same three suggested questions. Those are asked far more
-- often than anything else this system will ever be asked, and every one of
-- them is currently a full retrieval, an answer call and a verification call —
-- the same money spent to produce the same paragraph.
--
-- ## Why a table and not a column
--
-- `0009` and `0010` both cache onto `documents`, and both say why: one row per
-- document, always read with it, never queried by its contents. None of that
-- holds here. There are many answers per document, they are looked up by a key
-- the document does not know, and they expire independently.
--
-- ## What is in the key, and what is deliberately not
--
-- The key is (document_id, question fingerprint, prompt version, model). The
-- last two matter: an answer produced by `answer_v1` under a different model is
-- not the answer this deployment would give today, and serving it would make
-- the cache a way to silently ship a retired prompt. A prompt change therefore
-- misses every entry rather than invalidating them, which is the same thing
-- with less machinery.
--
-- The **user** is not in the key. Two people asking the same question of the
-- same sample get the same answer, because the answer is a property of the
-- document. It is not in the key for a second reason too: an entry keyed by
-- user would leak nothing, but an entry *shared* across users must not be
-- reachable for a document that is not shared — hence the sample-only rule
-- below, enforced in `api/answer_cache.py` rather than here, where it can be
-- tested.
--
-- ## Language is in the fingerprint, not beside it
--
-- The same question typed in Turkish and in English is two questions: they
-- retrieve differently and are answered in different languages. Normalisation
-- is case-folding and whitespace collapse only — no stemming, no stop-word
-- removal. "Deprem limiti nedir" and "deprem limiti ne" are different
-- questions and a cache that conflates them is a cache that answers the wrong
-- one.
create table answer_cache (
    document_id     uuid not null references documents (id) on delete cascade,
    -- sha256 of the normalised question plus its language. Stored rather than
    -- the question itself: the key is not meant to be read back, and a hash
    -- keeps an uploaded document's questions out of a table that outlives the
    -- conversation they came from.
    question_hash   text not null,
    prompt_version  text not null,
    model           text not null,

    payload         jsonb not null,
    created_at      timestamptz not null default now(),
    -- Bumped on every serve, so a sweep can drop what nobody asks for without
    -- dropping what everybody asks for.
    last_served_at  timestamptz not null default now(),
    serve_count     int not null default 0,

    primary key (document_id, question_hash, prompt_version, model)
);

-- Service-role only, like `app_settings`. Nothing reaches this table from the
-- browser: it is read and written by the answering path, which already checks
-- document access before it gets here.
alter table answer_cache enable row level security;

comment on table answer_cache is
  'Cached answers keyed by (document, question, prompt version, model). Samples only — see api/answer_cache.py. A cached answer is always labelled as one in the response.';

-- Age-out sweeps read by time, and the retention purge deletes by document,
-- which the foreign key already covers.
create index answer_cache_served_idx on answer_cache (last_served_at);
