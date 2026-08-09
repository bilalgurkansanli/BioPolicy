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
import re
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
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

# A thousands-separated amount: `3.630.000,00`, `1,271,820`, `550.000`. Requires
# a grouping separator, so `Madde 4.1` and `Article 7` are not matched — those
# are numbered headings and have to remain headings.
_MONEY = re.compile(r"\d{1,3}(?:([.,])\d{3})+(?:[.,]\d{1,2})?\b")

# Vertical gap between lines, as a multiple of the typical gap, above which a
# new paragraph starts.
PARAGRAPH_GAP_FACTOR = 1.5

# -----------------------------------------------------------------------------
# Column detection
# -----------------------------------------------------------------------------
# `extract_text_lines` groups glyphs by their vertical position, which is right
# for one column and destructive for two: a line from the left column and one
# from the right sit at the same y and are returned as a single line. Measured
# on the two-column sample before this existed, page 1 produced
#
#   "İşbu poliçe, sigortalı aracın çarpma, çarpışma, Madde 5 — İstisnalar
#    devrilme, yanma ve çalınması sonucu Aşağıdaki haller teminat ..."
#
# — the opening sentence of Article 1 with the *heading of Article 5* spliced
# into the middle of it. Not a formatting blemish: the sentence that reaches
# retrieval, embedding and finally the model is a sentence the document does not
# contain, and every clause on the page is corrupted the same way.
#
# The fix is to find the gutter and read each column separately. Detection is
# deliberately reluctant — a false positive would slice a single-column page in
# half down the middle, which is worse than the problem being solved, so all
# four conditions below must hold.

# The gutter must be at least this wide, relative to the page's text width. A
# two-column layout leaves a real channel; the space between two words does not.
MIN_GUTTER_RATIO = 0.035

# ...and it must sit near the middle. Columns in a policy document are equal
# width; an empty channel a fifth of the way across is a hanging indent or a
# margin note, not a column boundary.
GUTTER_CENTRE_TOLERANCE = 0.18

# Each side must carry at least this share of the page's words. A page with a
# wide right margin has an "empty column" that is simply blank.
MIN_COLUMN_WORD_SHARE = 0.2

# The share of *lines* allowed to cross the gutter before it stops being one.
#
# Not zero, and that is the whole difficulty. The first version of this asked
# for a strictly empty channel and found none on the very page it was written
# for: a centred title and a full-width schedule at the top of the page each
# span the gutter on their own, and one word is enough to mark a strip occupied.
# Density is the signal, not presence — a gutter is where *most lines* have
# nothing, while headers and spanning tables are a minority that legitimately
# cross it.
MAX_GUTTER_LINE_SHARE = 0.2


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

    # One pass per column, left to right, plus one for anything that spans them.
    # A single-column page detects one column, has nothing spanning, and takes
    # the identical path it always did.
    layout = _detect_columns(source, page)

    def spans(obj: dict[str, Any]) -> bool:
        centre = (float(obj["top"]) + float(obj["bottom"])) / 2
        return any(top - 0.5 <= centre <= bottom + 0.5 for top, bottom in layout.spanning)

    def extract(region: Any) -> None:
        try:
            lines = region.extract_text_lines()
        except Exception as exc:
            log.warning("line_extraction_failed", page=number, error=str(exc))
            return
        blocks.extend(_lines_to_blocks(lines, number, body_size))

    if layout.is_single:
        extract(source)
    else:
        if layout.spanning:
            extract(source.filter(spans))
        # The columns must not see the spanning lines again, or a title would
        # appear once whole and twice in halves.
        body = source.filter(lambda obj: not spans(obj))
        for left, right in layout.columns:
            extract(body.crop((left, 0, right, page.height)))

    # Reading order. Tables and prose are collected separately above, so the
    # page must be re-sorted or a coverage table would land after the article
    # that follows it.
    #
    # On one column this is top-to-bottom, as it always was. On two, sorting by
    # `top` alone would interleave the columns line by line — the same failure
    # as before, moved from the extractor to the sort — so blocks are grouped by
    # which column they sit in first and ordered within it second.
    #
    # Full-width blocks sort ahead of both columns. That is right for a header
    # or a schedule at the top of the page, which is where they occur in every
    # document this parser has seen; a full-width band *between* two columns
    # would be lifted above them, and is a layout to revisit if one ever shows
    # up rather than to speculate about now.
    blocks.sort(key=lambda b: (_column_of(b, layout), b.bbox.top if b.bbox else 0.0))
    return blocks


def _column_of(block: ParsedBlock, layout: ColumnLayout) -> int:
    """Which column a block belongs to. -1 for anything spanning them."""
    if layout.is_single or block.bbox is None:
        return 0
    for index, (left, right) in enumerate(layout.columns):
        if right is None:
            return index
        # Spanning is judged on the block's own extent, not on its centre: a
        # full-width table has its centre in the gutter and would otherwise be
        # assigned to whichever column the rounding favoured.
        if block.bbox.x0 >= left - 1.0 and block.bbox.x1 <= right + 1.0:
            return index
    return -1


@dataclass(frozen=True, slots=True)
class ColumnLayout:
    """How one page is divided, or that it is not divided at all."""

    columns: list[tuple[float, float | None]]
    """Left-to-right x bands. A single open-ended band means one column."""

    spanning: list[tuple[float, float]] = field(default_factory=list)
    """`(top, bottom)` of lines crossing the boundary — titles, wide tables."""

    @property
    def is_single(self) -> bool:
        return len(self.columns) < 2


def _detect_columns(source: Any, page: Any) -> ColumnLayout:
    """Find the column bands on a page, left to right.

    Returns a single open-ended band for a single-column page — the common case,
    which then takes exactly the path it took before this function existed.

    Rather than trusting one signal, every constant at the top of this module
    has to agree: the channel must be wide, near the middle, and flanked by real
    text on both sides. Detection failing closed costs nothing; detecting a
    column that is not there would cut a paragraph in half.
    """
    single = ColumnLayout(columns=[(0.0, None)])
    try:
        words = source.extract_words()
    except Exception:
        return single
    if len(words) < 12:
        return single

    left_edge = min(float(w["x0"]) for w in words)
    right_edge = max(float(w["x1"]) for w in words)
    text_width = right_edge - left_edge
    if text_width <= 0:
        return single

    # Sample the horizontal extent in narrow strips and count how many *lines*
    # cross each one. A strip is 1/200th of the text width — fine enough to
    # resolve a gutter, coarse enough not to see the space between two words.
    #
    # Counting lines rather than words is what makes a header survivable: a
    # centred title crossing the gutter contributes one line, while forty lines
    # of two-column body text contribute forty that do not.
    strips = 200
    strip_width = text_width / strips
    rows: dict[float, set[int]] = {}
    # Each line's own extent, kept alongside so the spanning lines can be
    # identified once the boundary is known without a second pass over words.
    bands: dict[float, tuple[float, float, float]] = {}
    for word in words:
        top = round(float(word["top"]), 1)
        row = rows.setdefault(top, set())
        start = int((float(word["x0"]) - left_edge) / strip_width)
        end = int((float(word["x1"]) - left_edge) / strip_width)
        row.update(range(max(0, start), min(strips - 1, end) + 1))

        x0, x1, bottom = float(word["x0"]), float(word["x1"]), float(word["bottom"])
        if top in bands:
            previous = bands[top]
            bands[top] = (min(previous[0], x0), max(previous[1], x1), max(previous[2], bottom))
        else:
            bands[top] = (x0, x1, bottom)

    if not rows:
        return single
    crossings = [0] * strips
    for occupied_strips in rows.values():
        for index in occupied_strips:
            crossings[index] += 1

    # Only the middle of the page is searched, and that restriction is doing
    # real work. The two columns are rarely equally full — on the sample, the
    # left carries 32 lines and the right 12 — so an absolute threshold marks
    # the *sparse right margin* as the widest quiet channel on the page and
    # picks it over the actual gutter. Constraining the search to the band a
    # gutter could plausibly occupy removes that failure by construction rather
    # than by tuning a threshold against it.
    ceiling = len(rows) * MAX_GUTTER_LINE_SHARE
    span = int(strips * GUTTER_CENTRE_TOLERANCE)
    lower, upper = strips // 2 - span, strips // 2 + span

    best: tuple[int, int] | None = None
    run_start: int | None = None
    for index in range(lower, upper + 1):
        quiet = index < upper and crossings[index] <= ceiling
        if quiet and run_start is None:
            run_start = index
        elif not quiet and run_start is not None:
            if best is None or index - run_start > best[1] - best[0]:
                best = (run_start, index)
            run_start = None

    if best is None:
        return single

    gutter_start = left_edge + best[0] * strip_width
    gutter_end = left_edge + best[1] * strip_width
    if (gutter_end - gutter_start) / text_width < MIN_GUTTER_RATIO:
        return single

    # The boundary goes through the quietest strip in the run, not through its
    # midpoint. The run can be lopsided — it extends into whichever column is
    # sparser — and its middle would then fall inside that column's text.
    quietest = min(range(best[0], best[1]), key=lambda i: crossings[i])
    centre = left_edge + (quietest + 0.5) * strip_width

    left_words = [w for w in words if float(w["x1"]) <= gutter_start + 1.0]
    right_words = [w for w in words if float(w["x0"]) >= gutter_end - 1.0]
    share = min(len(left_words), len(right_words)) / len(words)
    if share < MIN_COLUMN_WORD_SHARE:
        return single

    # Lines that cross the boundary belong to neither column — a centred title,
    # a full-width schedule. Cropping would cut them in half, and it did:
    # "KASKO SİGORTASI POLİÇESİ" came back as "KASKO SİGOR" and "RTASI
    # POLİÇESİ", two headings where the document has one. They are collected as
    # their own band instead, before either column.
    spanning: list[tuple[float, float]] = []
    for top, extent in bands.items():
        if extent[0] < centre - 1.0 and extent[1] > centre + 1.0:
            spanning.append((top, extent[2]))

    log.info(
        "two_column_page_detected",
        boundary=round(centre, 1),
        lines=len(rows),
        spanning_lines=len(spanning),
    )
    return ColumnLayout(
        columns=[(0.0, centre), (centre, float(page.width))],
        spanning=spanning,
    )


def _is_heading(line: dict[str, Any], body_size: float) -> tuple[bool, int]:
    chars = line.get("chars") or []
    if not chars:
        return False, 0

    text = line["text"].strip()
    # A heading is short. This guard is what stops a body paragraph that happens
    # to contain one large glyph from being promoted.
    if not text or len(text) > MAX_HEADING_CHARS:
        return False, 0

    # A line carrying a money amount is a schedule row, not a heading, whatever
    # its glyphs are doing.
    #
    # This cost a real document. An AXA home policy sets its coverage table in
    # bold, so "Deprem Bina 3.630.000,00" satisfied the bold-and-short rule
    # below and was classified as a heading — and the chunker puts a heading in
    # the *section path* rather than in the chunk's text. Of 28 amounts in that
    # policy, 25 sat in lines marked as headings, so exactly one reached
    # retrieval. Asked what the earthquake limit was, the system correctly
    # reported that it could not find one: the number had been read, parsed,
    # and then dropped on the floor between the parser and the chunker.
    #
    # Deliberately narrow. It matches a thousands-separated figure —
    # `3.630.000,00`, `1,271,820` — and not `Madde 4.1` or `Article 7`, which
    # are numbered headings and must stay headings.
    if _MONEY.search(text):
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
