"""Chunking guarantees.

The table-integrity tests here are the most valuable in the suite. Everything
downstream — retrieval, citation binding, the groundedness score — is built on
the assumption that a chunk is a coherent unit. A coverage table split mid-row
violates that silently: nothing errors, retrieval still returns something that
looks relevant, and the model produces a confident figure from the wrong row.
"""

from __future__ import annotations

import pytest

from api.ingest.chunker import Chunk, Chunker, count_tokens
from api.ingest.parsers import PdfParser
from api.ingest.types import BBox, ParsedBlock, ParsedDocument, ParsedPage


@pytest.fixture(name="konut_chunks")
async def konut_chunks_fixture(konut_pdf: bytes) -> list[Chunk]:
    return Chunker().chunk(await PdfParser().parse(konut_pdf))


@pytest.fixture(name="commercial_chunks")
async def commercial_chunks_fixture(commercial_pdf: bytes) -> list[Chunk]:
    return Chunker().chunk(await PdfParser().parse(commercial_pdf))


def _page(number: int = 1) -> ParsedPage:
    return ParsedPage(number=number, width=595.0, height=842.0)


def _doc(blocks: list[ParsedBlock], pages: int = 1) -> ParsedDocument:
    return ParsedDocument(blocks=blocks, pages=[_page(i + 1) for i in range(pages)])


# -----------------------------------------------------------------------------
# the central guarantee
# -----------------------------------------------------------------------------


def test_coverage_table_is_a_single_chunk(konut_chunks: list[Chunk]) -> None:
    matching = [c for c in konut_chunks if "Deprem ve Yanardağ Püskürmesi" in c.content]
    assert len(matching) == 1, "the coverage schedule was split across chunks"

    schedule = matching[0]
    assert schedule.content_type == "table"
    # Every peril must still sit beside its own limit.
    for peril, limit in [
        ("Yangın, Yıldırım, İnfilak", "2.500.000"),
        ("Deprem ve Yanardağ Püskürmesi", "1.800.000"),
        ("Sel ve Su Baskını", "750.000"),
        ("Ferdi Kaza (kişi başı)", "100.000"),
    ]:
        row = next(r for r in schedule.content.splitlines() if peril in r)
        assert limit in row


def test_a_table_is_never_split_even_when_oversized() -> None:
    """An oversized table stays whole. This is the rule, not a side effect."""
    rows = ["| Peril | Limit |", "| --- | --- |"]
    rows += [f"| Peril number {i} with a long descriptive name | {i * 1000} |" for i in range(400)]
    huge = "\n".join(rows)
    assert count_tokens(huge) > 700

    chunks = Chunker(target_tokens=700).chunk(
        _doc([ParsedBlock(kind="table", text=huge, page=1, bbox=BBox(0, 0, 100, 100))])
    )

    assert len(chunks) == 1
    assert chunks[0].content == huge
    assert chunks[0].token_count > 700  # deliberately oversized


def test_table_is_not_merged_with_neighbouring_prose() -> None:
    blocks = [
        ParsedBlock(kind="text", text="Prose before the table.", page=1, bbox=BBox(0, 0, 10, 10)),
        ParsedBlock(kind="table", text="| A | B |\n| --- | --- |\n| 1 | 2 |", page=1),
        ParsedBlock(kind="text", text="Prose after the table.", page=1, bbox=BBox(0, 30, 10, 40)),
    ]
    chunks = Chunker().chunk(_doc(blocks))

    table = next(c for c in chunks if c.content_type == "table")
    assert "Prose before" not in table.content
    assert "Prose after" not in table.content


# -----------------------------------------------------------------------------
# section context
# -----------------------------------------------------------------------------


def test_section_path_is_built_from_heading_hierarchy(konut_chunks: list[Chunk]) -> None:
    schedule = next(c for c in konut_chunks if "Deprem ve Yanardağ" in c.content)
    assert "Madde 1" in schedule.section_path
    assert "1.1 Teminat Tablosu" in schedule.section_path


def test_the_assembled_path_is_embedded_but_never_written_into_content(
    konut_chunks: list[Chunk],
) -> None:
    """Retrieval gets the assembled context; content stays what the page says.

    The risk this guards is precise: `section_path` is *built* — ancestors
    joined with `>` — and that string appears nowhere in the document. If it
    reached `content`, a model could quote it and citation binding would check
    the quote against text the PDF does not contain.

    A chunk's own heading is a different matter and is expected in `content`
    now: it is a real line of the document. Dropping it made bold schedule rows
    unsearchable, which cost a real policy 25 of its 28 coverage amounts.
    """
    exclusions = next(c for c in konut_chunks if "Savaş, iç savaş" in c.content)
    assert exclusions.section_path

    if " > " in exclusions.section_path:
        assert exclusions.section_path not in exclusions.content
    # The leaf heading may open the content; its ancestors must not be joined
    # into it.
    assert " > " not in exclusions.content
    assert exclusions.embed_text.startswith(exclusions.section_path)
    assert exclusions.content in exclusions.embed_text


def test_a_chunk_never_spans_a_heading() -> None:
    blocks = [
        ParsedBlock(kind="heading", text="Article 1", page=1, level=1, bbox=BBox(0, 0, 10, 5)),
        ParsedBlock(kind="text", text="Cover is granted.", page=1, bbox=BBox(0, 6, 10, 12)),
        ParsedBlock(kind="heading", text="Article 2", page=1, level=1, bbox=BBox(0, 14, 10, 19)),
        ParsedBlock(kind="text", text="Cover is withdrawn.", page=1, bbox=BBox(0, 20, 10, 26)),
    ]
    chunks = Chunker().chunk(_doc(blocks))

    assert len(chunks) == 2
    assert chunks[0].section_path == "Article 1"
    assert chunks[1].section_path == "Article 2"
    assert "withdrawn" not in chunks[0].content


def test_deeper_headings_nest_and_siblings_replace() -> None:
    blocks = [
        ParsedBlock(kind="heading", text="Madde 4", page=1, level=1),
        ParsedBlock(kind="heading", text="4.1 Genel", page=1, level=2),
        ParsedBlock(kind="text", text="Birinci istisna.", page=1),
        ParsedBlock(kind="heading", text="4.2 Özel", page=1, level=2),
        ParsedBlock(kind="text", text="İkinci istisna.", page=1),
        ParsedBlock(kind="heading", text="Madde 5", page=1, level=1),
        ParsedBlock(kind="text", text="Ödeme koşulları.", page=1),
    ]
    paths = [c.section_path for c in Chunker().chunk(_doc(blocks))]

    assert paths == ["Madde 4 > 4.1 Genel", "Madde 4 > 4.2 Özel", "Madde 5"]


# -----------------------------------------------------------------------------
# sizing
# -----------------------------------------------------------------------------


def test_prose_chunks_respect_the_token_budget(
    konut_chunks: list[Chunk], commercial_chunks: list[Chunk]
) -> None:
    for chunk in konut_chunks + commercial_chunks:
        if chunk.content_type == "table":
            continue  # tables are exempt by design
        assert chunk.token_count <= 700


def test_oversized_prose_is_split_on_sentence_boundaries() -> None:
    sentence = "Bu madde kapsamında teminat verilen haller aşağıda sayılmıştır. "
    long_text = sentence * 120
    assert count_tokens(long_text) > 700

    chunks = Chunker(target_tokens=300, overlap_tokens=50).chunk(
        _doc([ParsedBlock(kind="text", text=long_text, page=1, bbox=BBox(0, 0, 100, 700))])
    )

    assert len(chunks) > 1
    assert all(c.token_count <= 400 for c in chunks)  # target plus overlap slack
    # Geometry is inherited from the source block: we know which block a piece
    # came from, not where inside it.
    assert all(c.bbox is not None and c.page_start == 1 for c in chunks)


def test_overlap_must_be_smaller_than_the_target() -> None:
    with pytest.raises(ValueError, match="overlap"):
        Chunker(target_tokens=200, overlap_tokens=200)


def test_token_counting_reflects_turkish_density() -> None:
    """Documented in the module docstring; asserted so it stays true.

    Turkish costs materially more tokens than English for the same content. Any
    move to a character-based heuristic would silently produce Turkish chunks
    around twice the intended size.
    """
    tr = "Deprem ve Yanardağ Püskürmesi teminatı 1.800.000 TL limitle sınırlıdır."
    en = "Earthquake and volcanic eruption cover is limited to 1,800,000 TL."

    assert len(tr) == pytest.approx(len(en), abs=10)  # comparable character length
    assert count_tokens(tr) > count_tokens(en) * 1.5


# -----------------------------------------------------------------------------
# provenance
# -----------------------------------------------------------------------------


def test_every_chunk_is_traceable_to_a_page(
    konut_chunks: list[Chunk], commercial_chunks: list[Chunk]
) -> None:
    """A chunk that cannot be located in the document cannot be cited."""
    for chunk in konut_chunks + commercial_chunks:
        assert chunk.page_start >= 1
        assert chunk.page_end >= chunk.page_start
        assert chunk.content.strip()


def test_ordinals_are_dense_and_in_document_order(konut_chunks: list[Chunk]) -> None:
    assert [c.ordinal for c in konut_chunks] == list(range(len(konut_chunks)))
    assert [c.page_start for c in konut_chunks] == sorted(c.page_start for c in konut_chunks)


def test_bbox_is_confined_to_the_first_page_of_a_spanning_chunk() -> None:
    """A rectangle unioned across two pages points at neither of them."""
    blocks = [
        ParsedBlock(kind="text", text="Ends on page one.", page=1, bbox=BBox(10, 700, 200, 730)),
        ParsedBlock(kind="text", text="Starts on page two.", page=2, bbox=BBox(10, 40, 200, 70)),
    ]
    chunks = Chunker().chunk(_doc(blocks, pages=2))

    assert len(chunks) == 1
    chunk = chunks[0]
    assert (chunk.page_start, chunk.page_end) == (1, 2)
    assert chunk.bbox is not None
    assert chunk.bbox.top == 700 and chunk.bbox.bottom == 730


def test_empty_document_produces_no_chunks() -> None:
    assert Chunker().chunk(_doc([])) == []


def test_a_heading_is_content_as_well_as_a_path() -> None:
    """This assertion was inverted, deliberately, by a real document.

    It used to read `== []`, on the principle that a heading annotates its
    section rather than being content in its own right. An AXA home policy
    disproved it: the coverage schedule is set one bold row per line, the parser
    reads each row as a heading — correctly, they *are* set as headings — and
    filing them only in the section path made 25 of the document's 28 amounts
    unreachable by any search. The system then truthfully reported that it could
    not find the earthquake limit it had already parsed.

    A line of the document must be searchable, whatever weight it is set in.
    """
    blocks = [ParsedBlock(kind="heading", text="Deprem Bina 3.630.000,00", page=1, level=1)]

    chunks = Chunker().chunk(_doc(blocks))

    assert len(chunks) == 1
    assert "3.630.000,00" in chunks[0].content
