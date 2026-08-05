"""Detection and parsing, against the real sample PDFs.

These are not unit tests against mocks. They run the actual parser over the
actual committed fixtures, because the failure modes that matter here — a table
split mid-row, a Turkish character mangled into a question mark, a coverage
schedule duplicated into the prose — are all properties of real PDF bytes and
none of them reproduce against a stub.
"""

from __future__ import annotations

import pytest

from api.ingest.detector import NotAPdfError, detect, page_count
from api.ingest.parsers import PdfParser
from api.ingest.types import ParsedDocument
from api.tests.fakes import BlankOCRProvider, FakeOCRProvider

# -----------------------------------------------------------------------------
# detection
# -----------------------------------------------------------------------------


def test_native_document_is_detected_as_native(konut_pdf: bytes) -> None:
    result = detect(konut_pdf)
    assert result.source_type == "native"
    assert result.text_layer_ratio == 1.0
    # The cost-bearing assertion: nothing gets sent to the vision model.
    assert result.pages_needing_ocr == ()


def test_scanned_document_is_detected_as_scanned(scanned_pdf: bytes) -> None:
    result = detect(scanned_pdf)
    assert result.source_type == "scanned"
    assert result.text_layer_ratio == 0.0
    assert len(result.pages_needing_ocr) == result.page_count


def test_detector_rejects_non_pdf_bytes() -> None:
    with pytest.raises(NotAPdfError):
        detect(b"this is definitely not a pdf")


def test_page_count_is_available_without_parsing(commercial_pdf: bytes) -> None:
    """Upload validation needs the page count before committing to any work."""
    assert page_count(commercial_pdf) == 3


# -----------------------------------------------------------------------------
# native parsing
# -----------------------------------------------------------------------------


@pytest.fixture(name="konut")
async def konut_fixture(konut_pdf: bytes) -> ParsedDocument:
    return await PdfParser().parse(konut_pdf)


@pytest.fixture(name="commercial")
async def commercial_fixture(commercial_pdf: bytes) -> ParsedDocument:
    return await PdfParser().parse(commercial_pdf)


def _tables(document: ParsedDocument) -> list[str]:
    return [b.text for b in document.blocks if b.kind == "table"]


def test_turkish_characters_survive_extraction(konut: ParsedDocument) -> None:
    """The whole product is bilingual; a mangled ş makes retrieval silently worse."""
    combined = "\n".join(b.text for b in konut.blocks)
    for token in ("İstisnalar", "Yükümlülükleri", "Sigortalı", "Poliçe", "Yanardağ"):
        assert token in combined, f"{token!r} did not survive extraction"


def test_coverage_table_is_one_intact_block(konut: ParsedDocument) -> None:
    """The single most important parsing guarantee for this document class.

    In an insurance policy the coverage schedule *is* the answer to most
    valuable questions. A peril separated from its limit is worse than no
    answer, because it still looks like an answer.
    """
    schedule = next((t for t in _tables(konut) if "Deprem ve Yanardağ Püskürmesi" in t), None)
    assert schedule is not None, "coverage schedule was not extracted as a table"

    # Every peril and its limit must appear on the same line of the Markdown.
    expected = {
        "Yangın, Yıldırım, İnfilak": "2.500.000",
        "Deprem ve Yanardağ Püskürmesi": "1.800.000",
        "Sel ve Su Baskını": "750.000",
        "Hırsızlık ve Hırsızlığa Teşebbüs": "300.000",
        "Cam Kırılması": "25.000",
    }
    rows = schedule.splitlines()
    for peril, limit in expected.items():
        row = next((r for r in rows if peril in r), None)
        assert row is not None, f"{peril!r} missing from the schedule"
        assert limit in row, f"{peril!r} was separated from its limit {limit!r}"


def test_deductible_column_is_preserved(konut: ParsedDocument) -> None:
    """A third column is where naive table extraction usually collapses."""
    schedule = next(t for t in _tables(konut) if "Deprem ve Yanardağ Püskürmesi" in t)
    quake = next(r for r in schedule.splitlines() if "Deprem ve Yanardağ" in r)
    assert "%2 (asgari 5.000 TL)" in quake


def test_table_content_is_not_duplicated_into_prose(konut: ParsedDocument) -> None:
    """Tables are subtracted from the surrounding text.

    Without the subtraction every figure appears twice: once as a well-formed
    Markdown row and once as a column-less soup of numbers. The second copy
    competes with the first in retrieval and is exactly the context that
    produces a confident wrong figure.
    """
    prose = "\n".join(b.text for b in konut.blocks if b.kind != "table")
    assert "1.800.000" not in prose
    assert "2.500.000" not in prose


def test_headings_are_detected(konut: ParsedDocument) -> None:
    headings = [b.text for b in konut.blocks if b.kind == "heading"]
    assert any("Madde 4" in h and "İstisnalar" in h for h in headings)
    assert any("Madde 1" in h for h in headings)


def test_list_items_are_not_mistaken_for_headings(konut: ParsedDocument) -> None:
    """A bullet glyph is often set larger than body text.

    Taking the maximum glyph size per line promoted every exclusion in Article 4
    to a heading, which destroyed the section hierarchy precisely where the
    document is most load-bearing. Guarded here because the symptom (a slightly
    odd outline) is easy to miss by eye.
    """
    headings = [b.text for b in konut.blocks if b.kind == "heading"]
    assert not any(h.lstrip().startswith("•") for h in headings)
    assert not any("Savaş, iç savaş" in h for h in headings)


def test_exclusions_text_is_retained_somewhere(konut: ParsedDocument) -> None:
    """Reclassifying bullets must not silently drop them."""
    body = "\n".join(b.text for b in konut.blocks if b.kind == "text")
    assert "Savaş, iç savaş" in body
    assert "bodrum katlarda" in body  # the multi-clause flood interaction


def test_english_schedule_of_limits_survives(commercial: ParsedDocument) -> None:
    schedule = next((t for t in _tables(commercial) if "Business Interruption" in t), None)
    assert schedule is not None
    rows = schedule.splitlines()
    bi = next(r for r in rows if "Business Interruption" in r)
    assert "750,000" in bi
    assert "72 hours" in bi  # a deductible expressed as time, not money


def test_pages_are_one_based_and_bboxes_are_top_left(konut: ParsedDocument) -> None:
    # Deliberately not pinned to an exact page count: the sample document grows
    # when the eval needs a harder corpus, and a test that breaks on that is
    # asserting the fixture rather than the parser.
    assert konut.page_count >= 2
    assert {p.number for p in konut.pages} == set(range(1, konut.page_count + 1))

    for block in konut.blocks:
        assert block.page >= 1
        if block.bbox is not None:
            # Top-left origin: `top` is nearer the top of the page than `bottom`.
            assert block.bbox.top < block.bbox.bottom, f"flipped bbox on {block.kind}"
            assert block.bbox.x0 <= block.bbox.x1


def test_blocks_are_in_reading_order(konut: ParsedDocument) -> None:
    """Tables and prose are collected separately and must be re-interleaved."""
    for page in (1, 2):
        tops = [b.bbox.top for b in konut.blocks_on_page(page) if b.bbox]
        assert tops == sorted(tops), f"page {page} is out of reading order"


# -----------------------------------------------------------------------------
# OCR path
# -----------------------------------------------------------------------------


async def test_scanned_document_routes_every_page_to_ocr(scanned_pdf: bytes) -> None:
    detection = detect(scanned_pdf)
    ocr = FakeOCRProvider()

    document = await PdfParser(ocr=ocr).parse(scanned_pdf, pages_to_ocr=detection.pages_needing_ocr)

    assert ocr.call_count == detection.page_count
    assert all(p.ocr_used for p in document.pages)
    assert document.table_count >= 1  # the canned Markdown table was parsed


async def test_ocr_markdown_becomes_typed_blocks(scanned_pdf: bytes) -> None:
    document = await PdfParser(ocr=FakeOCRProvider()).parse(scanned_pdf, pages_to_ocr=(1,))

    kinds = {b.kind for b in document.blocks if b.page == 1}
    assert {"heading", "text", "table"} <= kinds

    table = next(b for b in document.blocks if b.kind == "table" and b.page == 1)
    assert "Yatarak Tedavi" in table.text
    assert "Limitsiz" in table.text


async def test_ocr_blocks_are_highlighted_at_page_level(scanned_pdf: bytes) -> None:
    """OCR gives no reliable geometry.

    Inventing a plausible rectangle would make citation highlighting *look*
    precise while pointing somewhere wrong, which is worse than honestly
    highlighting the whole page.
    """
    document = await PdfParser(ocr=FakeOCRProvider()).parse(scanned_pdf, pages_to_ocr=(1,))
    page = next(p for p in document.pages if p.number == 1)

    for block in document.blocks_on_page(1):
        assert block.bbox is not None
        assert block.bbox.x0 == 0.0
        assert block.bbox.bottom == pytest.approx(page.height)


async def test_blank_page_yields_no_blocks_rather_than_invention(scanned_pdf: bytes) -> None:
    ocr = BlankOCRProvider()
    document = await PdfParser(ocr=ocr).parse(scanned_pdf, pages_to_ocr=(1, 2))

    assert ocr.call_count == 2
    assert document.blocks == []


async def test_parser_refuses_ocr_work_without_a_provider(scanned_pdf: bytes) -> None:
    """Failing loudly beats silently producing an empty document."""
    with pytest.raises(RuntimeError, match="no OCRProvider"):
        await PdfParser().parse(scanned_pdf, pages_to_ocr=(1,))


async def test_native_pages_never_reach_ocr(konut_pdf: bytes) -> None:
    """The cost regression test: OCR is billed per page image."""
    ocr = FakeOCRProvider()
    detection = detect(konut_pdf)

    await PdfParser(ocr=ocr).parse(konut_pdf, pages_to_ocr=detection.pages_needing_ocr)

    assert ocr.call_count == 0
