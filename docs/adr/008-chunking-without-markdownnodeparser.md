# ADR 008 — Structure is tracked in our own parser output, not re-derived from Markdown

- **Status:** accepted
- **Date:** 2026-08-04
- **Phase:** 1

## Context

Section 5 of the spec is specific: chunk with `MarkdownNodeParser` to respect
heading hierarchy, then a sentence splitter for oversized nodes.

That prescription assumes the parser hands over a Markdown string. Ours does
not. `PdfParser` produces `ParsedBlock` objects that already carry `kind`
(heading / text / table), `level`, `page`, and `bbox`. To feed
`MarkdownNodeParser` we would have to serialise those blocks to Markdown and
re-parse them.

The re-parse is not free — it is lossy in the one dimension the product cannot
afford to lose. Markdown has nowhere to put a page number or a bounding box.
Everything downstream of chunking depends on that geometry: the citation chip
that scrolls the viewer to page 13 and highlights a rectangle, the `page` field
on every bound citation, the retrieval debug CLI. Round-tripping through
Markdown would mean reconstructing provenance by string-matching chunks back
against blocks, which is both fragile and pointless when we already hold the
answer.

## Decision

Heading hierarchy is tracked directly from `ParsedBlock.level` while walking the
document, building `section_path` as a stack. `MarkdownNodeParser` is not used.

`SentenceSplitter` **is** used, for its actual job: splitting an oversized text
block on sentence boundaries within a token budget, with overlap.

Its default sentence tokenizer is replaced with our own
(`api/ingest/sentences.py`). Three reasons, in the module's docstring: NLTK's
import guard rejects any module resolving under `Path.cwd()`, which under the
standard `uv` layout is every installed package; punkt is a runtime model
download and the whole parsing strategy exists to keep the image small; and
punkt is English-only, which is useless for half this corpus.

## Consequences

**Bought:** page numbers and bounding boxes survive chunking intact, so a
citation can be resolved to a rectangle on a page. Heading tracking is about
fifteen lines and is directly testable — `test_deeper_headings_nest_and_siblings_replace`
asserts the exact behaviour rather than trusting a library's interpretation of
our generated Markdown.

**Cost:** we own the heading-stack logic and the sentence splitter, including
their edge cases. The sentence splitter in particular is a regex over two
languages, and there will be constructions it gets wrong. It is covered by
twenty tests written against real policy text, which is the mitigation, not a
guarantee.

**This is a deliberate deviation from the spec** and is flagged as one. The
spec's intent — respect the document's own structure, do not split blindly on
token count — is fully honoured. Only the mechanism differs, because the
prescribed mechanism assumed an input shape we do not have.

## Alternatives considered

**Serialise to Markdown, parse with `MarkdownNodeParser`, then re-attach page
and bbox by matching chunk text back to blocks.** Follows the spec literally.
Rejected: the matching step is fuzzy string comparison, it fails on exactly the
content where blocks repeat similar wording, and it exists only to undo damage
we would have inflicted on ourselves one step earlier.

**Carry page and bbox through Markdown as HTML comments or custom attributes.**
Survives the round trip. Rejected as strictly more machinery than tracking a
stack of headings, for the same result.

**Hand-write the sentence splitting too, and drop `llama-index-core` entirely.**
Tempting once NLTK was removed — the remaining dependency does token-budgeted
windowing with overlap, which is real but not large. Kept for now because ADR
003 commits to it and it earns its place; revisit if the dependency causes
further friction.
