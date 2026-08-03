# Backlog

Ideas that came up during the build and were **deliberately not built**. Nothing
here is a promise. The point of this file is that a good idea arriving at the
wrong moment gets written down instead of built.

Grouped by why it was deferred.

---

## Out of scope for v1 by the spec

These were ruled out before the build started. Listed so the reasoning survives.

- **Multi-document comparison** — "how does this policy differ from my old one?"
  is the most requested feature this product doesn't have. It changes the
  retrieval model substantially: every query becomes multi-tenant across
  documents, and citations need document provenance as well as page.
- **Non-PDF formats** — DOCX, images, email.
- **Payment / subscription tiers.**
- **Team or sharing features.**
- **Fine-tuned or self-hosted models.**
- **Mobile native apps.**

---

## Deferred during the build

### Parsing
- **Docling as an alternative `DocumentParser`.** The interface exists precisely
  so this is a drop-in. Worth doing if the eval shows table-category recall
  lagging the other categories — see [ADR 002](./adr/002-pdf-parsing-stack.md).
- **Per-page routing for `mixed` documents.** v1 detects `native` / `scanned` /
  `mixed`, but treating an ambiguous document as scanned-if-in-doubt is simpler
  and safer than a page-level router. Revisit if real documents turn out to be
  mixed more often than expected.
- **Table continuation across page breaks.** A coverage schedule that spans
  pages 12–13 currently becomes two chunks. Detecting and stitching them is
  meaningful work and meaningfully better.

### Retrieval
- **A real cross-encoder reranker.** v1 ships a no-op or a cheap LLM filter, and
  the eval decides which. A hosted reranking API would likely beat both; it adds
  a fourth vendor and a per-query cost.
- **Query decomposition** for multi-part questions ("is flooding covered, and
  what's the deductible?"). Currently one retrieval per turn.
- **HyDE / hypothetical document embeddings.** Cheap to try, plausibly helps on
  the cross-lingual subset.
- **Tuning `CHUNK_TARGET_TOKENS` / `CHUNK_OVERLAP_TOKENS` against the eval set**
  rather than shipping the initial guess. This is a real gap, not a nice-to-have
  — the current values are stated in `constants.py` as untuned starting points.

### Generation
- **Streaming the verification pass** so groundedness appears progressively
  rather than at the end.
- **Answer caching** keyed on (document_id, normalised question). Would cut cost
  on the sample documents, which will receive the same questions repeatedly from
  demo visitors.

### Frontend
- **Highlighting the exact quote span** within a page, rather than the chunk's
  bounding box. Requires mapping the verified quote back to character offsets in
  the parsed text.
- **Keyboard navigation between citations.**
- **Dark mode.**
- **Export a conversation** as PDF or Markdown with citations intact.

### Operations
- **Structured cost attribution per conversation**, not just per user. Would make
  the "cost per query" figure in the eval report a live metric rather than a
  measured one.
- **Alerting on the budget breaker** beyond a log line.
- **A staging Supabase project seeded from a fixture** so integration tests can
  run in CI without touching either real project.

---

## Rejected outright, with reasons

Kept separate from "deferred" — these are things not to build later either.

- **OCR the first N pages of an oversized scan and answer from those.** Produces
  a system that confidently refuses about clauses it never read. See
  [ADR 005](./adr/005-ocr-page-cap.md).
- **Auto-selecting the newest model at startup.** Makes the model non-deterministic
  across deploys, which silently invalidates every number in the evaluation
  report. See [ADR 004](./adr/004-model-ids-are-verified-not-recalled.md).
- **Letting the model cite page numbers directly** instead of context-assembly
  IDs. Page numbers coming out of a model are unverifiable by construction;
  `[C1]`-style IDs can be checked mechanically against what was actually
  retrieved.
