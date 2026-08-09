"""Letterhead that repeats on every page.

A printed policy carries its insurer's address and product name on all of its
pages. The AXA document has two such lines on all 27, and the second is set in
bold — so the parser read it as a heading and the chunker opened a new chunk at
it, twenty-seven times.

Three costs, and only the first is obvious: tokens spent embedding text nobody
will ask about; chunk boundaries the document does not have; and 27 near-
identical vectors in a store that retrieval then has to rank against the clauses
that matter.
"""

from __future__ import annotations

from api.ingest.parsers.native import _strip_running_headers
from api.ingest.types import ParsedBlock, ParsedDocument, ParsedPage


def _document(*blocks: ParsedBlock) -> ParsedDocument:
    document = ParsedDocument()
    document.blocks.extend(blocks)
    # `page_count` is derived from `pages`, so the pages have to exist for the
    # majority test to have a denominator.
    highest = max((block.page for block in blocks), default=0)
    document.pages.extend(
        ParsedPage(number=number, width=595.0, height=842.0) for number in range(1, highest + 1)
    )
    return document


def _letterhead(page: int) -> ParsedBlock:
    return ParsedBlock(kind="text", text="AXA SİGORTA A.Ş. Meclisi Mebusan Cad.", page=page)


def _clause(page: int, text: str) -> ParsedBlock:
    return ParsedBlock(kind="text", text=text, page=page)


def test_a_line_on_every_page_is_removed() -> None:
    document = _document(*(_letterhead(page) for page in range(1, 9)))

    removed = _strip_running_headers(document)

    assert removed == 8
    assert document.blocks == []


def test_a_line_on_most_pages_is_still_removed() -> None:
    """A first page with its own masthead is normal; the footer below it is
    still a footer."""
    document = _document(
        *(_letterhead(page) for page in range(2, 9)),
        _clause(1, "Madde 1 — Teminat kapsamı."),
    )

    assert _strip_running_headers(document) == 7


def test_a_clause_appearing_twice_is_kept() -> None:
    """Repetition is only evidence when it is on *most* pages. Two mentions of
    the same exclusion across eight pages is a document, not a header."""
    document = _document(
        _clause(1, "Deprem hasarları istisnadır."),
        _clause(5, "Deprem hasarları istisnadır."),
        *(_clause(page, f"Madde {page}") for page in range(2, 9)),
    )

    assert _strip_running_headers(document) == 0


def test_a_repeated_table_is_never_removed() -> None:
    """A coverage schedule reprinted across pages answers most of the questions
    worth asking. Losing it to a header rule would be far worse than the noise
    the rule exists to remove."""
    schedule = "| Deprem | 1.800.000 |"
    document = _document(
        *(ParsedBlock(kind="table", text=schedule, page=page) for page in range(1, 9))
    )

    assert _strip_running_headers(document) == 0
    assert len(document.blocks) == 8


def test_a_short_document_is_left_alone() -> None:
    """On two pages, 'appears on most pages' means 'appears twice', which is
    something an ordinary clause does."""
    document = _document(_letterhead(1), _letterhead(2))

    assert _strip_running_headers(document) == 0


def test_page_numbers_are_not_treated_as_repeats() -> None:
    """They differ on every page, so they are not repeated text and this rule
    has nothing to say about them."""
    document = _document(*(_clause(page, f"Sayfa no :{page}") for page in range(1, 9)))

    assert _strip_running_headers(document) == 0
