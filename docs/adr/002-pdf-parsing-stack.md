# ADR 002 — PDF parsing on pypdfium2 + pdfplumber, not PyMuPDF, Unstructured or Docling

- **Status:** accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

Three things had to be true of the parsing layer, and they pull against each
other:

1. **Tables must survive.** In an insurance policy the coverage schedule *is*
   the answer to most valuable questions. A parser that flattens a limits table
   into prose destroys the thing users came for.
2. **Cold start must stay short.** The API runs on a scale-to-zero platform. Every
   megabyte of image is paid for by the first user after an idle period, and
   that user's impression is the product's impression.
3. **The repository is MIT.** It is a public portfolio piece and I want it to be
   commercially usable without a licensing conversation.

The original brief named Unstructured.io. Docling is the current open-source
accuracy leader on table extraction. PyMuPDF is the default recommendation
almost everywhere for fast text extraction with layout.

## Decision

Native-text parsing uses **pypdfium2** for text, page geometry and rasterisation,
and **pdfplumber** for table detection, serialising each table to a Markdown
table. Scanned pages go to a vision model behind an `OCRProvider` protocol. All
of it sits behind a `DocumentParser` protocol with at least one fake
implementation for tests.

## Consequences

**Bought:** no model weights, no system binaries — no poppler, no tesseract. The
runtime image is a slim Python base plus pure wheels, which keeps cold start in
the range where the progress indicator is enough to hold a user's attention.
Licence stays clean: pypdfium2 is Apache-2.0/BSD-3-Clause, PDFium is
BSD-3-Clause, pdfplumber is MIT.

**Cost, stated plainly:** this loses to Docling on complex tables — merged
cells, tables spanning a page break, and borderless tables laid out purely by
whitespace. I expect the eval harness to show it, and the per-category
breakdown in `eval/report.md` exists partly so that this specific weakness is
visible rather than averaged away. If table-lookup recall comes in materially
below the other categories, that is this decision's bill arriving, and the
`DocumentParser` interface is how we pay it.

**Revisit if:** table-category recall in the eval is the worst category by a
wide margin, or if the platform's cold-start behaviour turns out to tolerate a
much larger image than assumed.

## Alternatives considered

**PyMuPDF.** Genuinely the best fast text+layout extractor of the three, and my
first instinct. Rejected on licensing: it is AGPL-3.0 or commercial. Because
BioPolicy is served over a network, AGPL's network clause is engaged, and
shipping an MIT badge on a repository whose core parser is AGPL is the kind of
inconsistency a careful reviewer notices and a commercial adopter has to
unwind. pypdfium2 covers the same needs — text, bounding boxes, rendering to
raster for OCR — under a permissive licence. This was a deliberate downgrade in
convenience to keep the licence honest.

**Docling.** Best table accuracy available. Rejected for this timeline and this
platform: it pulls layout and table-structure models measured in hundreds of
megabytes to gigabytes. On scale-to-zero that is a cold-start tax on every idle
period, and it inverts the image-size budget the whole deployment strategy
depends on. Kept as the intended upgrade path behind `DocumentParser`.

**Unstructured.io.** Named in the original brief. Same objection as Docling for
the local high-accuracy strategies, plus its hosted API adds a third vendor,
another key to rotate and another per-page cost against a $30 ceiling.

**Vision OCR for every page, including native-text pages.** Simplest possible
pipeline — one code path, excellent table fidelity. Rejected on cost: it is the
most expensive operation available, billed per page image, and running it on
pages that already carry a perfectly good text layer is slower and usually
*less* accurate than reading that layer directly.
