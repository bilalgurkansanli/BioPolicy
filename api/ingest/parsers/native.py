"""The default `DocumentParser`: pdfplumber for content, pdfium for geometry.

Division of labour, and why:

* **pdfplumber** extracts text and detects tables. It is built on pdfminer.six,
  which is slow but gives per-character font size, weight and position — which
  is what makes heading detection possible at all. It also reports table
  bounding boxes, which is what lets us subtract tables from the prose.
* **pypdfium2** provides page count and rasterisation for the OCR path. It is a
  C library and is dramatically faster for whole-document passes.

The single most important behaviour in this file is that **a table's text is
removed from the surrounding prose**. Without that subtraction every figure in a
coverage schedule appears twice: once as a well-formed Markdown table and once
as a soup of numbers with no column headings. The second copy is worse than
useless — it competes with the good copy in retrieval and it is exactly the kind
of context that produces a confident wrong figure.
"""

from __future__ import annotations

import asyncio
import io
import statistics
import time
from collections.abc import Iterable
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

from api.constants import OCR_RENDER_DPI
from api.ingest.protocols import OCRProvider
from api.ingest.types import (
    BBox,
    OcrLine,
    ParsedBlock,
    ParsedDocument,
    ParsedPage,
    TranscribedPage,
)
from api.logging_config import get_logger

log = get_logger(__name__)

# A line whose glyphs are this many points larger than the document's body text
# is treated as a heading.
HEADING_SIZE_MARGIN = 0.6

# A short, fully-bold line is a heading even at body size — which is how most
# policy sub-headings ("1.1 Teminat Tablosu") are actually set.
MAX_BOLD_HEADING_CHARS = 90

# No heading in a policy document runs longer than this. Anything longer is a
# paragraph, whatever its glyphs are doing.
MAX_HEADING_CHARS = 120

# Vertical gap between lines, as a multiple of the typical gap, above which a
# new paragraph starts.
PARAGRAPH_GAP_FACTOR = 1.5


class PdfParser:
    """Parses native-text pages directly and routes scanned pages to OCR."""

    name = "pdfplumber+pdfium"

    def __init__(self, ocr: OCRProvider | None = None, *, ocr_concurrency: int = 4) -> None:
        self._ocr = ocr
        self._ocr_concurrency = ocr_concurrency

    async def _transcribe(self, rendered: dict[int, bytes]) -> dict[int, TranscribedPage]:
        """OCR every page, several at a time.

        Measured first: two pages of the scanned sample took **162 seconds**
        sequentially, roughly 80 seconds per page. At that rate the 30-page cap
        in ADR 005 would mean a forty-minute ingest, which makes the cap
        meaningless — nobody waits that long, and the progress indicator the
        spec promises would just be a very slow bar.
        The work is entirely network-bound, so it parallelises almost perfectly.

        Bounded rather than unbounded: firing thirty concurrent vision requests
        is the reliable way to hit a per-minute rate limit and turn a slow
        ingest into a failed one. Four keeps a 30-page document inside a couple
        of minutes while staying well under the quota.
        """
        assert self._ocr is not None
        semaphore = asyncio.Semaphore(self._ocr_concurrency)

        async def one(number: int, image: bytes) -> tuple[int, TranscribedPage]:
            async with semaphore:
                return number, await self._ocr.transcribe(image)  # type: ignore[union-attr]

        started = time.monotonic()
        results = await asyncio.gather(*(one(n, img) for n, img in sorted(rendered.items())))
        log.info(
            "ocr_complete",
            pages=len(rendered),
            concurrency=self._ocr_concurrency,
            seconds=round(time.monotonic() - started, 1),
        )
        return dict(results)

    async def parse(self, data: bytes, *, pages_to_ocr: tuple[int, ...] = ()) -> ParsedDocument:
        ocr_pages = set(pages_to_ocr)
        document = ParsedDocument()

        transcriptions: dict[int, TranscribedPage] = {}
        if ocr_pages:
            if self._ocr is None:
                raise RuntimeError(
                    "Document requires OCR but no OCRProvider is configured. "
                    "Set GEMINI_OCR_MODEL and GOOGLE_API_KEY, or reject the upload."
                )
            rendered = _render_pages(data, sorted(ocr_pages))
            transcriptions = await self._transcribe(rendered)

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            body_size = _body_font_size(pdf.pages)

            for index, page in enumerate(pdf.pages):
                number = index + 1
                width, height = float(page.width), float(page.height)
                needs_ocr = number in ocr_pages

                document.pages.append(
                    ParsedPage(
                        number=number,
                        width=width,
                        height=height,
                        has_text_layer=not needs_ocr,
                        ocr_used=needs_ocr,
                    )
                )

                if needs_ocr:
                    transcribed = transcriptions.get(number, TranscribedPage(markdown=""))
                    # The provider works in fractions of an image because it
                    # never sees a page size. This is the only place that knows
                    # one, so it is the only place the conversion belongs.
                    if transcribed.lines:
                        document.ocr_lines[number] = [
                            OcrLine(
                                text=line.text,
                                bbox=BBox(
                                    x0=line.bbox.x0 * width,
                                    top=line.bbox.top * height,
                                    x1=line.bbox.x1 * width,
                                    bottom=line.bbox.bottom * height,
                                ),
                            )
                            for line in transcribed.lines
                        ]
                    document.blocks.extend(
                        _blocks_from_markdown(
                            transcribed.markdown,
                            page=number,
                            width=width,
                            height=height,
                        )
                    )
                else:
                    document.blocks.extend(_blocks_from_page(page, number, body_size))

        log.info(
            "document_parsed",
            parser=self.name,
            pages=document.page_count,
            blocks=len(document.blocks),
            tables=document.table_count,
            ocr_pages=len(ocr_pages),
        )
        return document


# -----------------------------------------------------------------------------
# native page extraction
# -----------------------------------------------------------------------------


def _body_font_size(pages: Iterable[Any]) -> float:
    """The document's dominant glyph size.

    Measured across the whole document rather than per page, because a page that
    happens to be mostly heading would otherwise redefine "normal" and every
    real heading on it would be missed.
    """
    sizes: list[float] = []
    for page in pages:
        sizes.extend(round(float(c["size"]), 1) for c in page.chars)
    if not sizes:
        return 10.0
    try:
        return float(statistics.mode(sizes))
    except statistics.StatisticsError:  # pragma: no cover - mode is defined for non-empty
        return float(statistics.median(sizes))


def _table_bboxes(page: Any) -> list[tuple[float, float, float, float]]:
    try:
        return [tuple(float(v) for v in t.bbox) for t in page.find_tables()]  # type: ignore[misc]
    except Exception as exc:
        # Table detection is best-effort. A page whose ruling lines confuse
        # pdfplumber should still yield its prose, not fail the whole document.
        log.warning("table_detection_failed", page=page.page_number, error=str(exc))
        return []


def _blocks_from_page(page: Any, number: int, body_size: float) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    boxes = _table_bboxes(page)

    # --- tables -------------------------------------------------------------
    for table in page.find_tables() if boxes else []:
        try:
            rows = table.extract()
        except Exception as exc:
            log.warning("table_extraction_failed", page=number, error=str(exc))
            continue
        markdown = _rows_to_markdown(rows)
        if not markdown:
            continue
        x0, top, x1, bottom = (float(v) for v in table.bbox)
        blocks.append(
            ParsedBlock(
                kind="table",
                text=markdown,
                page=number,
                bbox=BBox(x0=x0, top=top, x1=x1, bottom=bottom),
            )
        )

    # --- prose, with table regions subtracted -------------------------------
    def outside_tables(obj: dict[str, Any]) -> bool:
        if obj.get("object_type") != "char":
            return True
        cx = (float(obj["x0"]) + float(obj["x1"])) / 2
        cy = (float(obj["top"]) + float(obj["bottom"])) / 2
        return not any(x0 <= cx <= x1 and top <= cy <= bottom for x0, top, x1, bottom in boxes)

    source = page.filter(outside_tables) if boxes else page

    try:
        lines = source.extract_text_lines()
    except Exception as exc:
        log.warning("line_extraction_failed", page=number, error=str(exc))
        lines = []

    blocks.extend(_lines_to_blocks(lines, number, body_size))

    # Reading order. Tables and prose are collected separately above, so the
    # page must be re-sorted top-to-bottom or a coverage table would land after
    # the article that follows it.
    blocks.sort(key=lambda b: (b.bbox.top if b.bbox else 0.0, b.bbox.x0 if b.bbox else 0.0))
    return blocks


def _is_heading(line: dict[str, Any], body_size: float) -> tuple[bool, int]:
    chars = line.get("chars") or []
    if not chars:
        return False, 0

    text = line["text"].strip()
    # A heading is short. This guard is what stops a body paragraph that happens
    # to contain one large glyph from being promoted.
    if not text or len(text) > MAX_HEADING_CHARS:
        return False, 0

    # WHY median rather than max: a single oversized glyph is common and means
    # nothing — a bullet character, a superscript footnote marker, a currency
    # symbol set in a different face. Taking the max made every bullet in an
    # exclusions list read as a heading, which shredded the section hierarchy
    # exactly where it matters most (Article 4 is where the exclusions live).
    # The median asks the more useful question: is *most of this line* set
    # larger than body text?
    line_size = statistics.median(float(c["size"]) for c in chars)
    bold_ratio = sum(1 for c in chars if "bold" in str(c.get("fontname", "")).lower()) / len(chars)

    if line_size >= body_size + HEADING_SIZE_MARGIN:
        # A bigger gap from body size implies a more prominent heading.
        return True, 1 if line_size >= body_size + 2.0 else 2
    if bold_ratio > 0.8 and len(text) <= MAX_BOLD_HEADING_CHARS:
        return True, 2
    return False, 0


def _lines_to_blocks(
    lines: list[dict[str, Any]], number: int, body_size: float
) -> list[ParsedBlock]:
    if not lines:
        return []

    gaps = [
        float(lines[i]["top"]) - float(lines[i - 1]["bottom"])
        for i in range(1, len(lines))
        if float(lines[i]["top"]) - float(lines[i - 1]["bottom"]) > 0
    ]
    typical_gap = statistics.median(gaps) if gaps else 0.0
    gap_threshold = max(typical_gap * PARAGRAPH_GAP_FACTOR, 1.0)

    blocks: list[ParsedBlock] = []
    buffer: list[dict[str, Any]] = []

    def flush() -> None:
        if not buffer:
            return
        text = " ".join(item["text"].strip() for item in buffer).strip()
        if text:
            blocks.append(
                ParsedBlock(kind="text", text=text, page=number, bbox=_union_bbox(buffer))
            )
        buffer.clear()

    previous: dict[str, Any] | None = None
    for line in lines:
        heading, level = _is_heading(line, body_size)
        if heading:
            flush()
            blocks.append(
                ParsedBlock(
                    kind="heading",
                    text=line["text"].strip(),
                    page=number,
                    bbox=_union_bbox([line]),
                    level=level,
                )
            )
            previous = line
            continue

        if previous is not None and float(line["top"]) - float(previous["bottom"]) > gap_threshold:
            flush()
        buffer.append(line)
        previous = line

    flush()
    return blocks


def _union_bbox(lines: list[dict[str, Any]]) -> BBox:
    box = BBox(
        x0=float(lines[0]["x0"]),
        top=float(lines[0]["top"]),
        x1=float(lines[0]["x1"]),
        bottom=float(lines[0]["bottom"]),
    )
    for line in lines[1:]:
        box = box.union(
            BBox(
                x0=float(line["x0"]),
                top=float(line["top"]),
                x1=float(line["x1"]),
                bottom=float(line["bottom"]),
            )
        )
    return box


def _rows_to_markdown(rows: list[list[str | None]]) -> str:
    """Serialise an extracted table to a Markdown table.

    Empty rows are dropped, `None` cells become empty strings, and newlines
    inside a cell are flattened — a literal newline would terminate the row and
    silently corrupt every column after it.
    """
    cleaned: list[list[str]] = []
    for row in rows:
        cells = [(cell or "").replace("\n", " ").replace("|", "\\|").strip() for cell in row]
        if any(cells):
            cleaned.append(cells)
    if not cleaned:
        return ""

    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]

    header, *body = cleaned
    out = ["| " + " | ".join(header) + " |", "|" + "|".join([" --- "] * width) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(out)


# -----------------------------------------------------------------------------
# OCR path
# -----------------------------------------------------------------------------


def _render_pages(data: bytes, numbers: list[int]) -> dict[int, bytes]:
    """Rasterise the given 1-based pages to PNG bytes for the OCR provider."""
    document = pdfium.PdfDocument(data)
    scale = OCR_RENDER_DPI / 72.0  # pdfium works in points; 72 to the inch.
    out: dict[int, bytes] = {}
    try:
        for number in numbers:
            bitmap = document[number - 1].render(scale=scale)
            buffer = io.BytesIO()
            bitmap.to_pil().convert("L").save(buffer, format="PNG", optimize=True)
            out[number] = buffer.getvalue()
    finally:
        document.close()
    return out


def _blocks_from_markdown(
    markdown: str, *, page: int, width: float, height: float
) -> list[ParsedBlock]:
    """Turn a vision model's Markdown for one page into blocks.

    Every block still gets the full page as its bounding box. Blocks are built
    from the Markdown, which carries no positions; the geometry the model
    reports is per *line* and is stored separately, so a citation is located at
    click time instead. Guessing which lines make up a block, in order to shrink
    this box, would be inventing precision — and a box that looks exact while
    pointing at the wrong clause is worse than one that is honestly the whole
    page.
    """
    full_page = BBox(x0=0.0, top=0.0, x1=width, bottom=height)
    blocks: list[ParsedBlock] = []
    paragraph: list[str] = []
    table: list[str] = []

    def flush_paragraph() -> None:
        text = " ".join(paragraph).strip()
        if text:
            blocks.append(ParsedBlock(kind="text", text=text, page=page, bbox=full_page))
        paragraph.clear()

    def flush_table() -> None:
        if table:
            blocks.append(
                ParsedBlock(kind="table", text="\n".join(table).strip(), page=page, bbox=full_page)
            )
        table.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("|"):
            flush_paragraph()
            table.append(stripped)
            continue
        flush_table()

        if not stripped:
            flush_paragraph()
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append(
                ParsedBlock(
                    kind="heading",
                    text=stripped.lstrip("#").strip(),
                    page=page,
                    bbox=full_page,
                    level=min(level, 6),
                )
            )
            continue

        paragraph.append(stripped)

    flush_table()
    flush_paragraph()
    return blocks
