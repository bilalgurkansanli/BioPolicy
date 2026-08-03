"""Citation binding — Section 7.2, and the mechanism this product is named for.

Every citation the model produces is treated as an unverified claim until it
passes two checks:

1. **Does the cited chunk exist in what we actually sent?** The model can only
   legitimately cite `[C1]`…`[Cn]` for chunks that made it into the assembled
   context. A citation naming `C9` when eight chunks were sent is a fabrication,
   and so is one naming a chunk that was retrieved but trimmed for budget.

2. **Does the quote appear in that chunk?** A model can name a real chunk and
   still attribute words to it that are not there — paraphrasing a clause into
   something firmer, or merging two clauses into one sentence that neither
   supports. Checking the quote catches this.

If **every** citation on an `answer_found: true` response is dropped, the answer
is not shown. It is downgraded to a refusal and recorded. That event is a caught
hallucination and it belongs in the metrics, not in front of a user.

## On fuzzy matching, and why character similarity alone is not enough

An exact substring test is too strict once OCR is involved: a scanned page turns
`1.800.000` into `1.8OO.OOO` often enough to matter, and rejecting an otherwise
honest citation over one glyph would punish users for their scanner rather than
for anything the model did. So an exact match is tried first and a similarity
fallback runs only if it fails.

But similarity alone gets this **exactly backwards**, and the failure is worth
spelling out because it is not obvious. Measured against
`Deprem teminatı 1.800.000 TL`:

| Candidate quote | Character similarity | What it actually is |
|---|---|---|
| `…1.8OO.OOO TL` | 0.88 | honest citation, scanner noise |
| `…9.900.000 TL` | 0.93 | **a different limit entirely** |

The fabrication scores *higher* than the honest citation, because swapping two
digits changes fewer characters than three `0→O` confusions. Any threshold that
admits the first admits the second.

The resolution is to stop treating digits as ordinary characters. In an
insurance policy a number is not a typo-tolerant token — it is the payload, and
the entire reason someone is reading the clause. So:

1. Known OCR letter/digit confusions are folded **only inside numeric runs**
   (`1.8OO.OOO` → `1.800.000`), which forgives the scanner without touching
   prose.
2. Every digit run in the quote must then still be present in the matched
   window. A quote claiming `9.900.000` against a chunk saying `1.800.000` is
   rejected no matter how similar the surrounding words are.

Fuzziness therefore applies to letters and never to figures.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from api.constants import CITATION_FUZZY_THRESHOLD
from api.generation.schemas import (
    AnswerPayload,
    BoundCitation,
    DroppedCitation,
)
from api.logging_config import get_logger
from api.retrieval.context import AssembledContext

log = get_logger(__name__)

_WHITESPACE = re.compile(r"\s+")

# Quote marks a model may wrap a span in, plus the typographic variants that
# appear when the source PDF used smart quotes. Stripped from both sides before
# comparison so a citation is never rejected over punctuation.
_TRIMMABLE = "\"'“”‘’«»‹›„‟ \t\n\r.,;:"

# Below this length a "quote" carries no evidential weight — a single word can
# be found in almost any chunk by chance, so matching one proves nothing.
MIN_QUOTE_CHARS = 12

# A run of characters that is trying to be a number: at least one real digit,
# possibly with OCR-confused letters and thousands separators around it. Applied
# after casefolding, so only lowercase forms need mapping.
_NUMERIC_RUN = re.compile(r"[0-9oilsb.,]*[0-9][0-9oilsb.,]*")

# Glyph confusions a scanner actually makes. Deliberately conservative, and
# deliberately applied only inside `_NUMERIC_RUN` — folding these across prose
# would turn "sol" into "501" and corrupt the text we are trying to verify.
_OCR_DIGITS = str.maketrans({"o": "0", "i": "1", "l": "1", "s": "5", "b": "8"})

_DIGIT_RUN = re.compile(r"\d+")


@dataclass(slots=True)
class BindingOutcome:
    """Result of binding one answer's citations."""

    kept: list[BoundCitation]
    dropped: list[DroppedCitation]
    suppressed: bool


def normalise(text: str) -> str:
    """Fold text to a form where only meaningful differences remain.

    NFKC first, because a PDF may encode `ﬁ` as a ligature and a model will type
    it as two letters. Then whitespace collapse — line wrapping inside a PDF is
    layout, not content, and a quote spanning a line break must still match.

    `casefold` rather than `lower`: it is the Unicode-correct operation. Note it
    is not Turkish-aware (`I` and `İ` do not fold the way a Turkish speaker
    would expect), but both sides of every comparison go through it identically,
    so the asymmetry cancels out.
    """
    folded = unicodedata.normalize("NFKC", text)
    return _WHITESPACE.sub(" ", folded).strip(_TRIMMABLE).casefold()


def fold_ocr_digits(text: str) -> str:
    """Repair scanner glyph confusions inside numbers, and nowhere else.

    `1.8OO.OOO` becomes `1.800.000`. The word `sol` is left alone, because the
    substitution only ever runs on a run that already contains a real digit.
    """
    return _NUMERIC_RUN.sub(lambda m: m.group(0).translate(_OCR_DIGITS), text)


def _digits_covered(needle: str, window: str) -> bool:
    """Every figure quoted must actually be present, as a multiset.

    This is the check that separates OCR noise from a wrong number. Character
    similarity cannot: swapping `1.800.000` for `9.900.000` changes fewer
    characters than three `0→O` scanner errors, so the fabrication scores higher
    than the honest citation.
    """
    remaining = _DIGIT_RUN.findall(window)
    for digits in _DIGIT_RUN.findall(needle):
        if digits in remaining:
            remaining.remove(digits)
        else:
            return False
    return True


def quote_appears_in(quote: str, content: str) -> tuple[bool, bool]:
    """Return (found, exact). `exact` is False for a fuzzy match."""
    needle = normalise(quote)
    haystack = normalise(content)

    if not needle or len(needle) < MIN_QUOTE_CHARS:
        return False, False

    if needle in haystack:
        return True, True

    # A quote longer than the chunk itself cannot be a span of it.
    if len(needle) > len(haystack):
        return False, False

    # Fuzzy fallback runs against OCR-repaired text on both sides, so scanner
    # noise is forgiven symmetrically.
    return _fuzzy_contains(fold_ocr_digits(needle), fold_ocr_digits(haystack)), False


def _fuzzy_contains(needle: str, haystack: str) -> bool:
    """Slide a window the size of the quote across the chunk.

    `SequenceMatcher.ratio()` over the whole chunk would be meaningless — a
    200-character quote inside a 3000-character chunk scores near zero however
    perfect the match. The comparison has to be local.

    The window steps by a quarter of the quote length, which is enough overlap
    that a true match cannot fall between two windows, and cheap enough that a
    handful of citations per answer costs nothing measurable.
    """
    span = len(needle)
    step = max(1, span // 4)

    for start in range(0, len(haystack) - span + 1, step):
        window = haystack[start : start + span]
        # Cheap rejection before the expensive comparison. Without it the scan
        # is a full O(n*m) diff against every window.
        if SequenceMatcher(None, needle, window).quick_ratio() < CITATION_FUZZY_THRESHOLD:
            continue
        if SequenceMatcher(None, needle, window).ratio() < CITATION_FUZZY_THRESHOLD:
            continue
        # Similar enough on characters — but a figure must never be approximate.
        # The window is widened slightly so a number sitting on the boundary is
        # not missed through pure alignment luck.
        neighbourhood = haystack[max(0, start - span // 4) : start + span + span // 4]
        if _digits_covered(needle, neighbourhood):
            return True

    return False


def bind(payload: AnswerPayload, context: AssembledContext) -> BindingOutcome:
    """Verify every citation against the context the model was actually given."""
    available = context.by_id
    kept: list[BoundCitation] = []
    dropped: list[DroppedCitation] = []

    for citation in payload.citations:
        chunk = available.get(citation.chunk_id)

        if chunk is None:
            # Either invented outright, or naming a chunk that was retrieved and
            # then trimmed for budget. Both mean the model cited something it
            # was not shown.
            dropped.append(
                DroppedCitation(
                    context_id=citation.chunk_id,
                    quote=citation.quote,
                    reason="unknown_chunk",
                )
            )
            continue

        found, exact = quote_appears_in(citation.quote, chunk.content)
        if not found:
            dropped.append(
                DroppedCitation(
                    context_id=citation.chunk_id,
                    quote=citation.quote,
                    reason="quote_not_found",
                )
            )
            continue

        kept.append(
            BoundCitation(
                chunk_id=chunk.chunk_id,
                context_id=citation.chunk_id,
                quote=citation.quote,
                # Page and geometry come from our record, never the model's.
                page=chunk.page_start,
                section_path=chunk.section_path,
                bbox=chunk.bbox.as_dict() if chunk.bbox else None,
                exact=exact,
            )
        )

    # The suppression rule. An answer that claims to have found something, and
    # whose every supporting citation turned out to be unverifiable, is not an
    # answer — it is a fluent guess.
    suppressed = bool(payload.answer_found and payload.citations and not kept)

    if dropped:
        log.warning(
            "citations_dropped",
            dropped=len(dropped),
            kept=len(kept),
            reasons=sorted({d.reason for d in dropped}),
            suppressed=suppressed,
        )
    if suppressed:
        log.warning("answer_suppressed", reason="no_valid_citations")

    return BindingOutcome(kept=kept, dropped=dropped, suppressed=suppressed)
