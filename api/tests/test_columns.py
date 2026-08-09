"""Two-column reading order.

The backlog called this the largest *unmeasured* gap in parsing, and it was
unmeasured for a structural reason: every sample document was single-column, so
the evaluation could not see the failure at all. It is not a formatting
blemish. `extract_text_lines` groups glyphs by vertical position, so a line from
the left column and one from the right come back as a single line, and the text
that reaches chunking, embedding and finally the model is text the document does
not contain.

Measured on `iki-sutun-kasko-tr.pdf` before the fix, page 1 produced:

    "İşbu poliçe, sigortalı aracın çarpma, çarpışma, Madde 5 — İstisnalar
     devrilme, yanma ve çalınması sonucu Aşağıdaki haller teminat ..."

— the opening sentence of Article 1 with the heading of Article 5 spliced into
the middle of it, and every clause on the page corrupted the same way.
"""

from __future__ import annotations

import hashlib

import pytest

from api.ingest.parsers.native import PdfParser


@pytest.fixture(name="parsed")
async def parsed_fixture(two_column_pdf: bytes) -> list[str]:
    document = await PdfParser().parse(two_column_pdf)
    return [" ".join(block.text.split()) for block in document.blocks]


def _find(blocks: list[str], needle: str) -> str:
    matches = [block for block in blocks if needle in block]
    assert matches, f"no block contains {needle!r}\n" + "\n".join(blocks)
    return matches[0]


# --- the failure this fixes ---------------------------------------------------


async def test_a_sentence_from_one_column_does_not_contain_the_other(
    parsed: list[str],
) -> None:
    """The exact corruption, asserted on the exact sentence it was found in."""
    opening = _find(parsed, "İşbu poliçe")

    assert "Madde 5" not in opening
    assert "İstisnalar" not in opening
    assert "devrilme, yanma ve çalınması" in opening


async def test_every_article_heading_survives_as_its_own_block(
    parsed: list[str],
) -> None:
    """Headings were being absorbed mid-sentence into the opposite column."""
    for article in ("Madde 1", "Madde 2", "Madde 3", "Madde 4", "Madde 5"):
        heading = _find(parsed, article)
        assert heading.startswith(article), f"{article} is buried inside {heading!r}"


async def test_the_left_column_is_read_before_the_right(parsed: list[str]) -> None:
    """Reading order, which sorting by `top` alone would still get wrong: it
    would interleave the two columns line by line rather than splicing them
    word by word — the same failure moved from the extractor to the sort."""
    deductible = parsed.index(_find(parsed, "Madde 2 — Muafiyetler"))
    exclusions = parsed.index(_find(parsed, "Madde 5 — İstisnalar"))

    assert deductible < exclusions


# --- what must not be broken to achieve it ------------------------------------


async def test_a_title_crossing_the_gutter_is_not_cut_in_half(
    parsed: list[str],
) -> None:
    """Cropping to columns split the centred title into "KASKO SİGOR" and
    "RTASI POLİÇESİ" — two headings where the document has one. Lines that
    cross the boundary belong to neither column and are read separately."""
    assert _find(parsed, "KASKO") == "KASKO SİGORTASI POLİÇESİ"


async def test_the_full_width_schedule_is_still_one_table(parsed: list[str]) -> None:
    table = _find(parsed, "KSK-2026-03310")

    assert table.startswith("|")
    assert "Poliçe Dönemi" in table


async def test_spanning_content_is_read_before_either_column(
    parsed: list[str],
) -> None:
    assert parsed.index(_find(parsed, "KASKO")) < parsed.index(_find(parsed, "Madde 1"))


# --- single-column documents are untouched ------------------------------------
#
# The risk of column detection is not that it fails to fire; it is that it fires
# when it should not and slices a paragraph down the middle. These hashes were
# taken from the parser before the change and must not move.


@pytest.mark.parametrize(
    ("fixture", "blocks", "digest"),
    [
        ("konut_pdf", 53, "0725a9df7f231792"),
        ("commercial_pdf", 23, "f5270136132ec6c9"),
    ],
)
async def test_single_column_output_is_byte_identical(
    request: pytest.FixtureRequest, fixture: str, blocks: int, digest: str
) -> None:
    document = await PdfParser().parse(request.getfixturevalue(fixture))
    joined = "\n".join(block.text for block in document.blocks)

    assert len(document.blocks) == blocks
    assert hashlib.sha256(joined.encode()).hexdigest()[:16] == digest
