"""Context assembly.

The invariant that matters: a chunk which did not make it into the prompt has no
`context_id`, and therefore cannot be successfully cited. Budget trimming and
citation validity are the same mechanism seen from two ends.
"""

from __future__ import annotations

from uuid import uuid4

from api.ingest.types import BBox
from api.retrieval.context import assemble
from api.retrieval.types import RetrievedChunk


def chunk(
    content: str,
    *,
    page: int = 1,
    page_end: int | None = None,
    section: str = "Madde 1",
    kind: str = "text",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        content=content,
        content_type=kind,
        page_start=page,
        page_end=page if page_end is None else page_end,
        section_path=section,
        bbox=BBox(10, 20, 300, 60),
    )


def test_ids_are_assigned_in_rank_order() -> None:
    chunks = [chunk(f"Clause number {i}.") for i in range(4)]
    result = assemble(chunks)

    assert [c.context_id for c in result.chunks] == ["C1", "C2", "C3", "C4"]
    assert "[C1]" in result.text
    assert "[C4]" in result.text


def test_header_carries_page_and_section() -> None:
    result = assemble([chunk("Sel teminatı bulunmaktadır.", page=12, section="Madde 4 > 4.7")])

    assert "page 12" in result.text
    assert "Madde 4 > 4.7" in result.text


def test_multi_page_chunk_shows_a_range() -> None:
    spanning = chunk("Spans a page break.")
    spanning.page_end = 3
    result = assemble([spanning])

    assert "pages 1–3" in result.text


def test_tables_are_marked_as_tables() -> None:
    result = assemble([chunk("| A | B |", kind="table")])
    assert "(table)" in result.text


def test_chunk_count_is_capped() -> None:
    chunks = [chunk(f"Clause {i}.") for i in range(20)]
    result = assemble(chunks, max_chunks=8)

    assert len(result.chunks) == 8
    assert len(result.dropped) == 12


def test_dropped_chunks_get_no_id_and_are_uncitable() -> None:
    """This is what makes budget trimming and citation validity one mechanism."""
    chunks = [chunk(f"Clause {i}.") for i in range(5)]
    result = assemble(chunks, max_chunks=2)

    assert all(c.context_id is not None for c in result.chunks)
    assert all(c.context_id is None for c in result.dropped)
    assert set(result.by_id) == {"C1", "C2"}


def test_token_budget_is_respected() -> None:
    """Chunks are admitted until the budget is spent, then dropped.

    Sized so the first chunk comfortably fits; the always-admit-the-best-chunk
    escape hatch is covered separately below.
    """
    medium = "Bu madde kapsamında teminat verilen haller aşağıda sayılmıştır. " * 10
    result = assemble([chunk(medium) for _ in range(10)], max_chunks=10, max_tokens=1000)

    assert result.token_count <= 1000
    assert 0 < len(result.chunks) < 10
    assert len(result.dropped) > 0


def test_the_best_chunk_is_admitted_even_if_it_alone_blows_the_budget() -> None:
    """An oversized coverage table is the chunk most likely to hold the answer.

    Returning an empty context because the top result was large would be the
    worst possible trade.
    """
    huge = "| Peril | Limit |\n" + "\n".join(f"| Peril {i} | {i}00.000 |" for i in range(500))
    result = assemble([chunk(huge, kind="table")], max_tokens=100)

    assert len(result.chunks) == 1
    assert result.token_count > 100


def test_empty_retrieval_produces_an_empty_context() -> None:
    result = assemble([])

    assert result.is_empty
    assert result.text == ""
    assert result.by_id == {}
