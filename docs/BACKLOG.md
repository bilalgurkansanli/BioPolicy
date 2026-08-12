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
- **Borderless tables as tables.** A real AXA policy sets its coverage schedule
  with alignment rather than ruled lines, so pdfplumber's line-based detection
  finds nothing and the rows arrive as prose. Retrieval and citation both work
  on it — `BİNA YANGIN 3.630.000,00` is retrieved first and quoted verbatim —
  so this is quality rather than a defect: Markdown structure would help a model
  keep figures attached to the right peril on a schedule wider than this one.

  **Not a drop-in change.** pdfplumber's `text` strategy was measured on the
  same document and reads a whole page as a 95×10 grid with 22% of cells filled,
  splitting the letterhead across columns. Any attempt needs a detector that
  fires only on genuine alignment, and the guard is the same one the column work
  used: the single-column samples must parse byte-identically.
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
- ~~**Multi-column reading order.**~~ **Done.** It was worse than this entry
  described. The damage was not in the sort but one level below it, in
  `extract_text_lines`, which groups glyphs by vertical position: a line from
  each column came back as *one line*, splicing "Madde 5 — İstisnalar" into the
  middle of Article 1's opening sentence. Fixing the sort alone would have
  changed nothing.

  Now detected per page and read column by column, with lines that cross the
  gutter — titles, full-width tables — collected separately so cropping does not
  cut them in half. Detection is deliberately reluctant, and the guard that
  matters is the last test in `api/tests/test_columns.py`: the parser's output
  on the single-column samples is asserted byte-identical to what it was before.

  Two things it still cannot do: three or more columns, and a full-width band
  *between* two columns, which is lifted above both rather than read in place.
  Neither occurs in any document this parser has seen, and both are cheap to add
  when one does.
- **Evaluate [`pdf-inspector`](https://github.com/firecrawl/pdf-inspector) as an
  alternative parser and detector.** MIT, Rust with abi3 manylinux wheels on
  PyPI, so no toolchain in the build. `classify_pdf` returns
  text_based/scanned/image_based/mixed with a confidence score and
  `pages_needing_ocr` — the same shape `detector.py` computes — and
  `extract_text_with_positions` returns per-item `x, y, width, height, font,
  font_size, page, is_bold, item_type`. That last one is the interesting part:
  it would replace the median-glyph-size heading heuristic with real font
  metadata, and it claims multi-column reading order, which is the gap above.

  **Not swapped, deliberately.** Chunk boundaries would change, invalidating
  every stored embedding, and this project's own rule is that pipeline changes
  get measured. The corpus cannot measure this one: three synthetic
  single-column documents where the table category already scores 100%. Swapping
  a parser we cannot evaluate for another we cannot evaluate is not an
  improvement, it is a coin flip with a re-ingestion attached.

  **The trigger** is a real-world PDF corpus that the current parser visibly
  fails on — a two-column policy would do it. At that point the swap is cheap:
  the `DocumentParser` interface exists for exactly this ([ADR 002](./adr/002-pdf-parsing-stack.md)),
  and the honest experiment is both parsers over the same golden set with the
  retrieval numbers published side by side.

### Retrieval
- **A floor that can separate answerable from unanswerable.** The one that
  shipped cannot, and the measurement in `api/retrieval/floor.py` says why: those
  two populations overlap almost completely in embedding distance. It separates
  on-topic from off-topic, which is a narrower claim than the idea started with.
  Closing the real gap needs a signal that is not distance — the entailment
  check in ADR 014 is the closest thing this codebase already has.
- **Identifier-only queries can fall outside the floor.** `1.800.000` and `%20`
  land at 0.73–0.80 in the Voyage space against a threshold of 0.72; in the
  Gemini space every such probe sat inside it, which is what retired the keyword
  veto. Reinstating the veto does not help — those queries matched 1 chunk each
  while "Ignore previous instructions" matched 7 — so this needs the same
  not-distance signal as the item above. A question *containing* an identifier
  is unaffected; only a query that is nothing else.
- **Nothing measures the floor except a script somebody remembers to run.** The
  threshold silently stopped matching its embedding space for the whole of the
  Voyage migration, and the only symptom was users being told their document
  said nothing about subjects it discussed at length. `check_model` now refuses
  to boot on a mismatch, which catches a *changed model* — it does not catch a
  drifted corpus, a re-chunking, or a threshold that was never right. A periodic
  `measure_floor` run with the answerable-refusal count as a tripwire would.
- **A real cross-encoder reranker.** v1 ships a no-op or a cheap LLM filter, and
  the eval decides which. A hosted reranking API would likely beat both; it adds
  a fourth vendor and a per-query cost.
- **Query decomposition** for multi-part questions ("is flooding covered, and
  what's the deductible?"). Still one retrieval per turn — the understanding
  stage now writes a single query naming every part, which was enough for the
  case that prompted it because both figures sat in adjacent passages. A
  document that scatters the parts needs real decomposition and a fusion across
  several retrievals.
- ~~**Understand a question that is not shaped like a query.**~~ **Done.**
  `rewrite_v1` only ran when there was conversation history, so a first-turn
  question got no help — and that is where the failure was. "Peki diyelim ki
  deprem oldu ve ev tamamen yıkıldı. Ne kadar para veriliyor?" put the passage
  carrying both figures at fused rank 13 against a window of 8; the document
  answers it on page one and the model never saw it. `understand_v1` strips the
  scaffolding, and the stage now fires on a first-turn question whose shape says
  it needs one — over 96 characters, or more than one sentence, both derived
  from the golden set. Short direct questions still skip the call entirely.
- **HyDE / hypothetical document embeddings.** Cheap to try, plausibly helps on
  the cross-lingual subset.
- **Decide whether query rewriting earns its latency.** The rewrite call is
  currently measured at 8-11s against a 6.0s median for the whole answer, so the
  5s ceiling in `constants.py` means the fallback — the question as typed — is
  the common path on follow-ups. Either the call gets fast (a smaller model, a
  shorter prompt, a warmer client) or rewriting should be dropped rather than
  left as a tax that mostly times out. This needs a multi-turn eval subset,
  which does not exist yet: the golden dataset is single-turn.
- **Tuning `CHUNK_TARGET_TOKENS` / `CHUNK_OVERLAP_TOKENS` against the eval set**
  rather than shipping the initial guess. This is a real gap, not a nice-to-have
  — the current values are stated in `constants.py` as untuned starting points.

### Generation
- **Streaming the verification pass** so groundedness appears progressively
  rather than at the end.
- ~~**Answer caching**~~ **Done.** Keyed on (document, normalised question,
  prompt version, model), samples only, and always labelled as cached in the
  response — a stored answer served in milliseconds for nothing would otherwise
  quietly contradict the latency and cost figures the report publishes. See
  `api/answer_cache.py`.

### Frontend
- **Keyboard navigation between citations.**
- **A text layer over the PDF canvas**, so the document is selectable and
  searchable. pdf.js renders one; the viewer currently draws pixels only.
- **Export a conversation** as PDF or Markdown with citations intact.

### Evaluation — what the 2×2 run left open

The first run proved nothing because the corpus never stressed the system. The
second one — longer documents, a naive-prompt arm — produced a real finding:
**the strict prompt does the work and the mechanisms change no decisions while
adding ~55% to the cost.** These are the open threads from that.

- **A check on the inferential step.** The naive prompt's failures are correct
  citations supporting conclusions the document never draws — a real theft
  clause quoted accurately, then stretched to cover a car. Binding validates the
  quote and verification validates the claim against the excerpt; neither asks
  whether the *inference* follows. This is the highest-value item in this file
  and the one the measurement actually pointed at.
- **Exercise the half of binding that has never fired.** Citation validity is
  100% in every arm partly because a provider-enforced JSON schema makes an
  invented chunk id near-impossible. An arm with the schema constraint dropped
  would show whether quote-checking catches anything on its own.
- **Decide whether the mechanisms earn their cost.** On current evidence they do
  not: no decision changed, ~55% more per question. Either find the conditions
  where they pay for themselves, or make them optional and say so. Keeping an
  unmeasured safeguard because it feels prudent is the habit this project exists
  to argue against.
- **Questions whose answer spans more than the context budget**, so the trimming
  path in context assembly is exercised — at 21 chunks against a window of 8 it
  now trims, but no question yet needs a chunk that got trimmed.
- **A deliberately noisier scan** — lower DPI, skew, speckle — to see where the
  OCR path degrades rather than assuming 200 DPI clean renders are typical.

### Operations
- **Record embedding calls in `usage_events`.** They are the one provider call
  the ledger never sees: `api/ingest/pipeline.py` embeds a whole document
  without writing a usage row, so the spend counter and the budget breaker both
  under-report by the cost of every ingest. `voyage-4-lite` is also absent from
  `Settings.priced_models`, so `/api/health` will not even report it as
  `unpriced` — invisible in both directions.

  **The obstacle that justified this is gone.** Under Gemini it was real rather
  than laziness: the endpoint reported `billable_character_count` while the rate
  card is per *token*, and converting between them would have been the fabricated
  number `api/pricing.py` refuses on principle. Voyage returns
  `usage.total_tokens` — the provider's own figure, in the unit its rate card
  uses — and `VoyageEmbedder.total_tokens` already accumulates it. What remains
  is a verified rate in `MODEL_PRICES` and a usage row at the end of the ingest.
  This moved from "blocked on a number nobody has" to "not done yet", which is a
  different entry in this file and should be read as one.
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
