-- What a document tried to tell the system that read it.
--
-- Written once, at ingest, by `api/ingest/injection.py`. Null means the scan has
-- not run (documents ingested before this migration); an empty array means it
-- ran and found nothing. The distinction matters in the interface: "checked,
-- clean" and "not checked" must not look the same to a user deciding whether to
-- trust an answer.
--
-- jsonb rather than text[] because each finding carries three fields — which
-- rule matched, why that rule exists, and the excerpt to show the user — and
-- flattening them into parallel arrays would be a join waiting to go wrong.
--
-- Deliberately not indexed. Nothing queries by it; it is read with the document
-- row it belongs to, and an index on a column with a handful of non-empty values
-- is maintenance cost for no lookup.
alter table documents
  add column if not exists injection_findings jsonb;

comment on column documents.injection_findings is
  'Instruction-shaped text found in this document at ingest. null = not scanned, [] = scanned and clean. Advisory only: the document is still served, and the answering path is what actually resists the text.';
