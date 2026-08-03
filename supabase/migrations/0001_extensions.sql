-- 0001 — extensions
--
-- Migrations are numbered and forward-only. Never edit one that has been
-- applied; write a new one that corrects it.

-- Vector similarity search.
create extension if not exists vector;

-- gen_random_uuid(). Present by default on modern Postgres, declared for clarity.
create extension if not exists pgcrypto;

-- Scheduled jobs: the ingestion queue watchdog (ADR 007) and the retention
-- purge. Supabase installs this into the `extensions` schema.
create extension if not exists pg_cron;

-- Outbound HTTP from Postgres, so a cron job can call our own API. Required by
-- 0007; both the queue sweep and the retention purge go through the API rather
-- than manipulating storage directly.
create extension if not exists pg_net;

-- Trigram matching, used by the citation-binding fallback when a quote has to
-- be located in a chunk that OCR rendered imperfectly.
create extension if not exists pg_trgm;
