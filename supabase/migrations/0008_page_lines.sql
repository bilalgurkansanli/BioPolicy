-- 0008 — where the lines of a scanned page sit
--
-- A page with a text layer needs nothing stored: PDF.js can find any quote in
-- the page itself at click time. A scan cannot — every character is a pixel —
-- so the only geometry that will ever exist for it is what the vision model
-- reported while reading, and it exists only during ingestion.
--
-- Without this table a citation on a scanned page can be highlighted no more
-- precisely than "somewhere on this sheet of paper", which is what the whole
-- page box in `chunks` means. With it, the same locator that works against a
-- text layer works against OCR output.
--
-- Rows only exist for pages that actually went through OCR. A native document
-- writes nothing here.

create table page_lines (
  id          bigserial primary key,
  document_id uuid not null references documents(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,

  page        int  not null,
  -- One visual row of text. In a table each cell is its own line, which is what
  -- makes a coverage row highlightable cell by cell rather than as a band.
  content     text not null,

  -- Top-left origin, PDF points, page-relative — the same convention as
  -- `chunks.bbox` and `api/ingest/types.py`. Stored as columns rather than
  -- JSONB because nothing ever reads one corner without the other three.
  x0          real not null,
  top         real not null,
  x1          real not null,
  bottom      real not null,

  constraint page_lines_page_positive check (page >= 1),
  constraint page_lines_box_ordered check (x1 > x0 and bottom > top)
);

-- The only access pattern: every line on one page of one document.
create index page_lines_document_page_idx on page_lines (document_id, page);

alter table page_lines enable row level security;

-- Mirrors the chunks policy exactly. A leak here leaks document content in the
-- same way — these rows are the document, cut into lines.
create policy page_lines_select_own_or_sample on page_lines
  for select using (
    auth.uid() = user_id
    or exists (select 1 from documents d where d.id = page_lines.document_id and d.is_sample)
  );

-- Written only by the ingestion pipeline, which uses the service role. The
-- absence of an insert policy for regular users is deliberate.

comment on table page_lines is
  'Line geometry for OCR''d pages, so a citation can highlight the clause '
  'rather than the page. Empty for documents with a text layer.';
