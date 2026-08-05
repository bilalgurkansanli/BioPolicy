"""Citation binding — the most important tests in this repository.

Every claim BioPolicy makes about trustworthiness reduces to the behaviour
asserted here. If binding is wrong, the citation chips in the UI become
decorative, the groundedness score measures nothing, and the evaluation report
is a fiction.
"""

from __future__ import annotations

import pytest

from api.generation.citations import bind, fold_ocr_digits, normalise, quote_appears_in
from api.generation.schemas import AnswerPayload, Citation
from api.retrieval.context import AssembledContext, assemble
from api.tests.test_context import chunk

FLOOD = (
    "Sel ve su baskını teminatı; yağmur, kar erimesi, taşkın veya deniz kabarması "
    "nedeniyle suyun risk adresine girmesi sonucu oluşan zararları karşılar."
)
QUAKE_TABLE = (
    "| Teminat | Limit (TL) | Muafiyet |\n"
    "| --- | --- | --- |\n"
    "| Deprem ve Yanardağ Püskürmesi | 1.800.000 | %2 (asgari 5.000 TL) |\n"
    "| Sel ve Su Baskını | 750.000 | 3.500 TL |"
)


def context_of(*contents: str) -> AssembledContext:
    return assemble([chunk(c, page=i + 1) for i, c in enumerate(contents)])


def answer(
    *citations: Citation, found: bool = True, text: str = "Evet, kapsanıyor."
) -> AnswerPayload:
    return AnswerPayload(answer_found=found, answer=text, citations=list(citations))


# -----------------------------------------------------------------------------
# the happy path
# -----------------------------------------------------------------------------


def test_a_verbatim_quote_is_kept() -> None:
    ctx = context_of(FLOOD)
    outcome = bind(answer(Citation(chunk_id="C1", quote="suyun risk adresine girmesi")), ctx)

    assert len(outcome.kept) == 1
    assert outcome.dropped == []
    assert not outcome.suppressed
    assert outcome.kept[0].exact is True


def test_page_and_geometry_come_from_our_record_not_the_model() -> None:
    """A model-supplied page number is unverifiable; ours is a lookup.

    This is what makes a citation chip safe to make clickable.
    """
    ctx = context_of("First chunk of text goes here.", FLOOD)
    outcome = bind(answer(Citation(chunk_id="C2", quote="deniz kabarması")), ctx)

    citation = outcome.kept[0]
    assert citation.page == 2
    assert citation.bbox == {"x0": 10.0, "top": 20.0, "x1": 300.0, "bottom": 60.0}
    assert citation.chunk_id == ctx.chunks[1].chunk_id


def test_a_citation_reports_the_whole_page_range_of_its_chunk() -> None:
    """The quote is not always on the page the chunk starts on.

    A chunk that runs past a page break can be quoted from the far side of it.
    With only the starting page, the viewer searched one sheet, found nothing,
    and fell back to highlighting all of it — an exclusion halfway down page two
    lighting up the whole of page one. The range is what tells it where the
    quote can possibly be, and where it cannot.
    """
    ctx = assemble([chunk(FLOOD, page=4, page_end=5)])
    outcome = bind(answer(Citation(chunk_id="C1", quote="deniz kabarması")), ctx)

    citation = outcome.kept[0]
    assert citation.page == 4
    assert citation.page_end == 5


def test_a_single_page_chunk_reports_the_same_page_twice() -> None:
    """No special case at the other end: the range is always a range."""
    ctx = assemble([chunk(FLOOD, page=7)])
    outcome = bind(answer(Citation(chunk_id="C1", quote="deniz kabarması")), ctx)

    assert (outcome.kept[0].page, outcome.kept[0].page_end) == (7, 7)


@pytest.mark.parametrize("written", ["C1", "[C1]", "c1", " C1 ", "[c1]"])
def test_citation_id_formatting_variants_all_resolve(written: str) -> None:
    """Models are inconsistent about this. A format quirk is not a fabrication."""
    ctx = context_of(FLOOD)
    outcome = bind(answer(Citation(chunk_id=written, quote="taşkın veya deniz kabarması")), ctx)

    assert len(outcome.kept) == 1


def test_quote_spanning_a_line_break_still_matches() -> None:
    """Line wrapping inside a PDF is layout, not content."""
    ctx = context_of("Sigortalı beş iş günü içinde\nsigortacıya bildirimde bulunur.")
    outcome = bind(
        answer(Citation(chunk_id="C1", quote="beş iş günü içinde sigortacıya bildirimde")), ctx
    )

    assert len(outcome.kept) == 1


def test_a_quote_from_a_table_row_is_bindable() -> None:
    """Table figures are the highest-value citations in this document class."""
    ctx = context_of(QUAKE_TABLE)
    outcome = bind(
        answer(Citation(chunk_id="C1", quote="Deprem ve Yanardağ Püskürmesi | 1.800.000")), ctx
    )

    assert len(outcome.kept) == 1


# -----------------------------------------------------------------------------
# catching fabrication
# -----------------------------------------------------------------------------


def test_citing_a_chunk_that_was_never_sent_is_dropped() -> None:
    ctx = context_of(FLOOD)
    outcome = bind(answer(Citation(chunk_id="C7", quote="suyun risk adresine girmesi")), ctx)

    assert outcome.kept == []
    assert outcome.dropped[0].reason == "unknown_chunk"


def test_citing_a_chunk_trimmed_for_budget_is_dropped() -> None:
    """Retrieved is not the same as shown. Only what was shown is citable."""
    ctx = assemble(
        [chunk(FLOOD), chunk("Bodrum katlarda sel zararları kapsam dışıdır.")], max_chunks=1
    )
    assert len(ctx.dropped) == 1

    outcome = bind(answer(Citation(chunk_id="C2", quote="Bodrum katlarda sel zararları")), ctx)

    assert outcome.dropped[0].reason == "unknown_chunk"


def test_a_plausible_but_absent_quote_is_dropped() -> None:
    """The core catch: a real chunk, cited with words it does not contain.

    This is what a model does when it paraphrases a clause into something firmer
    than the document actually says.
    """
    ctx = context_of(FLOOD)
    outcome = bind(
        answer(Citation(chunk_id="C1", quote="sel teminatı sınırsız olarak karşılanır")), ctx
    )

    assert outcome.kept == []
    assert outcome.dropped[0].reason == "quote_not_found"


def test_a_figure_the_document_does_not_contain_is_rejected() -> None:
    """The costliest possible hallucination in an insurance document."""
    ctx = context_of(QUAKE_TABLE)
    outcome = bind(
        answer(Citation(chunk_id="C1", quote="Deprem ve Yanardağ Püskürmesi | 3.500.000")), ctx
    )

    assert outcome.kept == []


def test_a_quote_borrowed_from_a_different_chunk_is_rejected() -> None:
    """Attributing chunk two's words to chunk one is still a fabrication."""
    ctx = context_of(FLOOD, "Hırsızlık teminatı 300.000 TL ile sınırlıdır.")
    outcome = bind(answer(Citation(chunk_id="C1", quote="Hırsızlık teminatı 300.000 TL")), ctx)

    assert outcome.dropped[0].reason == "quote_not_found"


def test_a_single_word_is_not_evidence() -> None:
    """A one-word 'quote' can be found in almost any chunk by chance."""
    ctx = context_of(FLOOD)
    outcome = bind(answer(Citation(chunk_id="C1", quote="sel")), ctx)

    assert outcome.kept == []


# -----------------------------------------------------------------------------
# the suppression rule
# -----------------------------------------------------------------------------


def test_an_answer_whose_every_citation_fails_is_suppressed() -> None:
    """A caught hallucination. Counted, not hidden."""
    ctx = context_of(FLOOD)
    outcome = bind(
        answer(
            Citation(chunk_id="C1", quote="deprem teminatı bulunmamaktadır"),
            Citation(chunk_id="C4", quote="tamamen kapsam dışıdır"),
        ),
        ctx,
    )

    assert outcome.kept == []
    assert len(outcome.dropped) == 2
    assert outcome.suppressed is True


def test_one_surviving_citation_prevents_suppression() -> None:
    ctx = context_of(FLOOD)
    outcome = bind(
        answer(
            Citation(chunk_id="C1", quote="suyun risk adresine girmesi sonucu"),
            Citation(chunk_id="C9", quote="invented entirely"),
        ),
        ctx,
    )

    assert len(outcome.kept) == 1
    assert len(outcome.dropped) == 1
    assert outcome.suppressed is False


def test_a_refusal_is_not_suppressed() -> None:
    """`answer_found: false` with no citations is correct behaviour, not failure."""
    ctx = context_of(FLOOD)
    outcome = bind(answer(found=False, text="Bu belge iş kesintisi teminatından söz etmiyor."), ctx)

    assert outcome.suppressed is False
    assert outcome.kept == []


def test_an_answer_with_no_citations_at_all_is_not_suppressed_here() -> None:
    """Uncited answers are the verifier's problem, not the binder's.

    Suppressing here would conflate 'cited falsely' with 'did not cite', and the
    two need to be distinguishable in the evaluation report.
    """
    ctx = context_of(FLOOD)
    outcome = bind(answer(found=True, text="Evet."), ctx)

    assert outcome.suppressed is False


# -----------------------------------------------------------------------------
# OCR tolerance
# -----------------------------------------------------------------------------


def test_ocr_noise_does_not_invalidate_an_honest_citation() -> None:
    """A scanner turning 0 into O should not be charged to the model."""
    ctx = context_of("Deprem teminatı 1.800.000 TL ile sınırlıdır ve muafiyet uygulanır.")
    outcome = bind(
        answer(Citation(chunk_id="C1", quote="Deprem teminatı 1.8OO.OOO TL ile sınırlıdır")), ctx
    )

    assert len(outcome.kept) == 1
    assert outcome.kept[0].exact is False  # surfaced, not hidden


def test_tolerance_does_not_extend_to_a_different_figure() -> None:
    """The line between OCR noise and a wrong number has to hold."""
    ctx = context_of("Deprem teminatı 1.800.000 TL ile sınırlıdır ve muafiyet uygulanır.")
    outcome = bind(
        answer(Citation(chunk_id="C1", quote="Deprem teminatı 9.900.000 TL ile sınırlıdır")), ctx
    )

    assert outcome.kept == []


# -----------------------------------------------------------------------------
# normalisation helpers
# -----------------------------------------------------------------------------


class TestNormalisation:
    def test_collapses_whitespace(self) -> None:
        assert normalise("a   b\n\tc") == "a b c"

    def test_strips_surrounding_quote_marks(self) -> None:
        assert normalise("  “Sigortalı beş iş günü.”  ") == normalise("Sigortalı beş iş günü")

    def test_folds_compatibility_forms(self) -> None:
        """A PDF may encode a ligature the model will type as separate letters."""
        assert normalise("ﬁnancial") == normalise("financial")

    def test_quote_longer_than_the_chunk_cannot_match(self) -> None:
        found, _ = quote_appears_in("a" * 500, "short chunk text here")
        assert found is False

    @pytest.mark.parametrize("empty", ["", "   ", "\n"])
    def test_empty_quote_never_matches(self, empty: str) -> None:
        found, _ = quote_appears_in(empty, FLOOD)
        assert found is False


class TestOcrDigitFolding:
    """Scanner repair must be confined to numbers.

    Folding these substitutions across prose would corrupt the very text we are
    verifying against — which would make the binder complicit in exactly the
    failure it exists to catch.
    """

    def test_confused_glyphs_inside_a_number_are_repaired(self) -> None:
        assert fold_ocr_digits("1.8oo.ooo") == "1.800.000"

    def test_prose_is_left_alone(self) -> None:
        for word in ("sol", "bilesi", "istisna", "sigortalı"):
            assert fold_ocr_digits(word) == word

    def test_a_run_without_any_digit_is_untouched(self) -> None:
        assert fold_ocr_digits("bkz. ilgili madde") == "bkz. ilgili madde"

    def test_digit_multiset_guard_rejects_a_substituted_figure(self) -> None:
        """The check that character similarity cannot make."""
        chunk_text = "Deprem teminatı 1.800.000 TL ile sınırlıdır ve muafiyet uygulanır."
        honest, exact = quote_appears_in("Deprem teminatı 1.8OO.OOO TL", chunk_text)
        fabricated, _ = quote_appears_in("Deprem teminatı 9.900.000 TL", chunk_text)

        assert (honest, exact) == (True, False)
        assert fabricated is False

    def test_an_extra_figure_not_in_the_chunk_is_rejected(self) -> None:
        chunk_text = "Hırsızlık teminatı 300.000 TL ile sınırlıdır."
        found, _ = quote_appears_in("Hırsızlık teminatı 300.000 TL, muafiyet 1.000 TL", chunk_text)
        assert found is False
