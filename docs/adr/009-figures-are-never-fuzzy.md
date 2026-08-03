# ADR 009 — Citation matching is fuzzy on letters and exact on figures

- **Status:** accepted
- **Date:** 2026-08-04
- **Phase:** 3

## Context

Citation binding checks that a quoted span actually appears in the chunk it is
attributed to. An exact substring test is too strict once OCR is in play: a
scanned page renders `1.800.000` as `1.8OO.OOO` often enough to matter, and
rejecting an honest citation over three glyphs punishes the user for their
scanner.

So the natural design is a similarity threshold. That design is wrong, and the
way it fails is worth recording because it is counter-intuitive.

Measured against the chunk text `Deprem teminatı 1.800.000 TL ile sınırlıdır`,
using `difflib.SequenceMatcher`:

| Candidate quote | Similarity | What it actually is |
|---|---|---|
| `Deprem teminatı 1.8OO.OOO TL ile sınırlıdır` | **0.88** | honest citation, scanner noise |
| `Deprem teminatı 9.900.000 TL ile sınırlıdır` | **0.93** | a different limit entirely |

The fabrication scores *higher* than the honest citation. Swapping two digits
changes fewer characters than three `0→O` confusions, so no threshold exists
that admits the first and rejects the second. Both of our first two tests failed
simultaneously — one for being too strict, one for being too loose — which is
what surfaced this.

The underlying error is treating a number as ordinary text. In an insurance
policy the number is not incidental to the clause; it is the reason anyone is
reading the clause.

## Decision

Two mechanisms, applied in order, both only on the fuzzy fallback path:

1. **OCR glyph repair, confined to numeric runs.** `o→0`, `i/l→1`, `s→5`, `b→8`,
   applied only inside a run that already contains a real digit. `1.8OO.OOO`
   becomes `1.800.000`; the word `sol` is untouched. Confining the substitution
   is essential — folding it across prose would corrupt the very text we are
   verifying against.

2. **A digit multiset guard.** After a window clears the similarity threshold,
   every digit run in the quote must still be present in that window's
   neighbourhood. A quote claiming `9.900.000` against a chunk saying
   `1.800.000` is rejected regardless of how similar the surrounding words are.

Fuzziness therefore applies to letters and never to figures.

## Consequences

**Bought:** the two cases are now cleanly separated, and separated for a
principled reason rather than by a tuned constant. A citation carrying a
fabricated limit cannot pass binding no matter how well the rest of the sentence
matches. Honest citations from scanned documents still pass, and are marked
`exact: false` so the UI can show that the match was approximate rather than
hiding it.

**Cost:** a legitimate quote that reformats a figure — writing `1.800.000 TL` as
`1,800,000 TL`, or `1.8 milyon` — will be rejected. That is the correct
direction to fail in, but it is a real false-negative class and it will show up
in the evaluation as a dropped citation on an otherwise good answer. Worth
watching in `eval/report.md`.

The guard also assumes figures are the load-bearing content. That holds for
insurance policies and contracts. It would be the wrong rule for prose where
numbers are incidental.

**Revisit if:** the eval shows citation-validity losses concentrated on
correctly-answered questions, which would mean the guard is firing on
reformatting rather than on fabrication.

## Alternatives considered

**Raise the similarity threshold.** Does not work — the fabrication scores
higher than the honest citation, so raising the bar rejects the honest one
first.

**Drop fuzzy matching, require exact substrings.** Clean and defensible, and
genuinely tempting. Rejected because it makes the OCR path near-useless: nearly
every citation from a scanned document would be dropped, every such answer would
be suppressed, and the product would appear to refuse constantly on exactly the
documents it advertises support for. That is a worse failure than the one being
prevented, and it would be invisible in the metrics — it looks like admirable
caution.

**Normalise all digits away before comparing.** Would make `1.800.000` and
`9.900.000` identical. This is the bug, stated as a feature.
