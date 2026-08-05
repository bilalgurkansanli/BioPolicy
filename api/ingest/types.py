"""The normalised representation every parser produces.

A `DocumentParser` — whether it reads a text layer, calls a vision model, or is
a fake in a test — must produce a `ParsedDocument`. Everything downstream
(chunking, embedding, citation binding, the PDF viewer's highlighting) depends
only on this shape, which is what makes the parser genuinely swappable.

## Coordinates

**All bounding boxes use a top-left origin, in PDF points, page-relative.**
`(x0, top, x1, bottom)` with `top < bottom`.

This needs saying because the two libraries involved disagree. PDF's native
coordinate system, which pdfium exposes, puts the origin at the bottom-left and
measures upward. pdfplumber flips this to top-left. Browsers and PDF.js think
top-left. We normalise to top-left at the boundary, once, here — rather than
letting two conventions travel through the codebase and meet in the highlighting
code, where a flipped box looks like a rendering bug rather than a units bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "text", "table"]
SourceType = Literal["native", "scanned", "mixed"]


@dataclass(frozen=True, slots=True)
class BBox:
    """A rectangle on a page, top-left origin, PDF points."""

    x0: float
    top: float
    x1: float
    bottom: float

    def as_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "top": self.top, "x1": self.x1, "bottom": self.bottom}

    def union(self, other: BBox) -> BBox:
        return BBox(
            x0=min(self.x0, other.x0),
            top=min(self.top, other.top),
            x1=max(self.x1, other.x1),
            bottom=max(self.bottom, other.bottom),
        )

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(slots=True)
class ParsedBlock:
    """One coherent unit of a document.

    `text` is Markdown for tables and plain text otherwise. Tables are Markdown
    because it survives tokenisation as a *structure* — an LLM reading a
    pipe-delimited table can still tell which limit belongs to which peril,
    which a whitespace-aligned dump does not reliably preserve.
    """

    kind: BlockKind
    text: str
    page: int  # 1-based, matching what a user sees in a viewer
    bbox: BBox | None = None
    # Heading depth, 1-based. Only meaningful when kind == "heading".
    level: int | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError(f"page is 1-based; got {self.page}")


@dataclass(slots=True)
class ParsedPage:
    number: int  # 1-based
    width: float
    height: float
    # Whether this specific page carried an extractable text layer. Drives
    # per-page routing for 'mixed' documents.
    has_text_layer: bool = True
    # True when this page's content came from OCR rather than a text layer.
    # Surfaced to the UI so a user can weigh a citation from a noisy scan
    # differently from one lifted out of a clean text layer.
    ocr_used: bool = False


@dataclass(frozen=True, slots=True)
class OcrLine:
    """One visual row of text on a page that had to be transcribed.

    A page with a text layer needs nothing like this: PDF.js can find any quote
    in the page itself. A scan cannot — every character is a pixel — so the only
    geometry that will ever exist for it is what the vision model reports while
    reading. Storing it is what lets a citation on a scanned page highlight the
    clause instead of the whole sheet of paper.

    In a table each cell is its own line, which is what makes a coverage row
    highlightable cell by cell.
    """

    text: str
    bbox: BBox


@dataclass(frozen=True, slots=True)
class TranscribedPage:
    """What a vision model read off one rendered page.

    `lines` carry boxes as **fractions of the page** (0.0-1.0), not points: the
    provider sees an image and has no idea what size the page is. The parser,
    which does, converts them.
    """

    markdown: str
    lines: tuple[OcrLine, ...] = ()


@dataclass(slots=True)
class ParsedDocument:
    blocks: list[ParsedBlock] = field(default_factory=list)
    pages: list[ParsedPage] = field(default_factory=list)
    # Only for pages that went through OCR, keyed by 1-based page number.
    ocr_lines: dict[int, list[OcrLine]] = field(default_factory=dict)
    source_type: SourceType = "native"
    # ISO 639-1, filled in by language detection after parsing.
    detected_lang: str | None = None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_characters(self) -> int:
        return sum(len(b.text) for b in self.blocks)

    @property
    def full_text(self) -> str:
        """Every block's text, in reading order, for whole-document scanning.

        Joined with newlines rather than spaces so that a pattern anchored to a
        sentence cannot run across a block boundary and match two unrelated
        clauses as though they were one.
        """
        return "\n".join(b.text for b in self.blocks)

    @property
    def table_count(self) -> int:
        return sum(1 for b in self.blocks if b.kind == "table")

    def blocks_on_page(self, page: int) -> list[ParsedBlock]:
        return [b for b in self.blocks if b.page == page]


@dataclass(frozen=True, slots=True)
class PageTextStats:
    """What the detector measured on a single page."""

    number: int
    char_count: int
    has_text_layer: bool


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Outcome of native-vs-scanned classification.

    `pages_needing_ocr` is the list the cost cap is applied to — it is the
    number of *page images* that will be billed, which is not the same as the
    document's page count for a mixed document.
    """

    source_type: SourceType
    page_count: int
    text_layer_ratio: float
    pages: tuple[PageTextStats, ...]

    @property
    def pages_needing_ocr(self) -> tuple[int, ...]:
        if self.source_type == "native":
            return ()
        if self.source_type == "scanned":
            return tuple(p.number for p in self.pages)
        # Mixed: only the pages that actually lack a text layer. Never OCR a
        # page that already has text — it is slower and usually worse.
        return tuple(p.number for p in self.pages if not p.has_text_layer)
