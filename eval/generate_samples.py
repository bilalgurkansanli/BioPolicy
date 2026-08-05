"""Generate the three bundled sample PDFs from `sample_content.py`.

    python -m eval.generate_samples

Run this whenever `sample_content.py` changes. The generated PDFs **are**
committed — they are fixtures for the parser tests and the documents the public
demo serves without an upload, so a reviewer cloning the repo must get exactly
the bytes the eval report was produced against.

Two documents are written as native-text PDFs. The third is rasterised into an
image-only PDF, which is what makes the scanned/OCR branch of the pipeline
testable at all. Without it, that path stays unexercised until a real user
uploads a scan.

Fonts: Bitstream Vera, bundled with reportlab under a permissive licence. It is
used rather than a system font because the output is committed to a public
repository, and it covers the full Turkish character set (ş ğ ı İ) — verified,
not assumed.
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import reportlab
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from eval.sample_content import ALL_DOCUMENTS, HARD_DOCUMENTS

OUTPUT_DIR = Path(__file__).parent / "golden" / "samples"

# Rasterisation settings for the simulated scan. 150 DPI is typical of an office
# scanner and is deliberately not generous — if the OCR path only works on
# pristine 300 DPI renders, that is worth finding out here rather than in
# production.
SCAN_DPI = 150


def _register_fonts() -> tuple[str, str]:
    """Register Vera regular and bold. Returns their reportlab names."""
    fonts_dir = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("Vera", str(fonts_dir / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("Vera-Bold", str(fonts_dir / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("Vera", normal="Vera", bold="Vera-Bold")
    return "Vera", "Vera-Bold"


def _styles(regular: str, bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PolicyTitle",
            parent=base["Title"],
            fontName=bold,
            fontSize=16,
            leading=20,
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "PolicySubtitle",
            parent=base["Normal"],
            fontName=regular,
            fontSize=10.5,
            leading=14,
            alignment=1,
            textColor=colors.HexColor("#444444"),
            spaceAfter=6 * mm,
        ),
        "h1": ParagraphStyle(
            "PolicyH1",
            parent=base["Heading1"],
            fontName=bold,
            fontSize=12,
            leading=16,
            spaceBefore=6 * mm,
            spaceAfter=2.5 * mm,
        ),
        "h2": ParagraphStyle(
            "PolicyH2",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=10.5,
            leading=14,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "PolicyBody",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=9.5,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=2.5 * mm,
        ),
        "cell": ParagraphStyle(
            "PolicyCell",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=8.5,
            leading=11,
            spaceAfter=0,
        ),
        "cellhead": ParagraphStyle(
            "PolicyCellHead",
            parent=base["BodyText"],
            fontName=bold,
            fontSize=8.5,
            leading=11,
            spaceAfter=0,
            textColor=colors.white,
        ),
    }


def _meta_table(meta: list[tuple[str, str]], st: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(f"<b>{k}</b>", st["cell"]), Paragraph(v, st["cell"])] for k, v in meta]
    table = Table(rows, colWidths=[45 * mm, 110 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f2f2")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _content_table(rows: list[list[str]], st: dict[str, ParagraphStyle]) -> Table:
    """Render a coverage/limits table with visible ruling lines.

    WHY ruled rather than whitespace-aligned: pdfplumber's default table
    detection keys off drawn lines. A borderless table is markedly harder to
    detect, and while real policies contain both kinds, the fixtures need to
    test the *pipeline* rather than the hardest possible edge case. Borderless
    table extraction is a known weakness, recorded in ADR 002 and the backlog.
    """
    body = [
        [Paragraph(c, st["cellhead"] if r == 0 else st["cell"]) for c in row]
        for r, row in enumerate(rows)
    ]
    table = Table(body, colWidths=[85 * mm, 40 * mm, 40 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f4858")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_story(doc: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = [
        Paragraph(doc["title"], st["title"]),
        Paragraph(doc["subtitle"], st["subtitle"]),
        _meta_table(doc["meta"], st),
        Spacer(1, 6 * mm),
    ]

    for kind, payload in doc["blocks"]:
        if kind == "h1":
            story.append(Paragraph(payload, st["h1"]))
        elif kind == "h2":
            story.append(Paragraph(payload, st["h2"]))
        elif kind == "p":
            story.append(Paragraph(payload, st["body"]))
        elif kind == "list":
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(item, st["body"]), leftIndent=6 * mm) for item in payload],
                    bulletType="bullet",
                    bulletFontName=st["body"].fontName,
                    start="•",
                    leftIndent=6 * mm,
                )
            )
            story.append(Spacer(1, 2 * mm))
        elif kind == "table":
            # KeepTogether so the schedule is not split across a page break by
            # the renderer. The chunker must also refuse to split it — that is a
            # separate guarantee, tested separately.
            story.append(KeepTogether(_content_table(payload, st)))
            story.append(Spacer(1, 3 * mm))
        elif kind == "pagebreak":
            story.append(PageBreak())
        else:  # pragma: no cover - guards a typo in sample_content
            raise ValueError(f"unknown block kind: {kind!r}")

    return story


def _render_native(doc: dict[str, Any], st: dict[str, ParagraphStyle]) -> bytes:
    buffer = io.BytesIO()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=doc["title"],
        author="BioPolicy synthetic sample",
        subject="Synthetic policy document for evaluation. Not a real insurance policy.",
    )
    template.build(_build_story(doc, st))
    return buffer.getvalue()


def _render_two_column(doc: dict[str, Any], st: dict[str, ParagraphStyle]) -> bytes:
    """The same content, flowed through two frames instead of one.

    This is the layout `api/ingest/parsers/native.py` gets wrong: it sorts
    blocks by `(top, x0)`, so a two-column page comes back as left line 1, right
    line 1, left line 2 — interleaved into prose that reads like nothing. The
    parser has always done this and the evaluation has never been able to see
    it, because every document in the corpus was one column.

    The header spans the full width, as it does on a real policy, so the
    document also exercises a page whose top is one column and whose body is
    two.
    """
    buffer = io.BytesIO()
    template = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=doc["title"],
        author="BioPolicy synthetic sample",
        subject="Synthetic policy document for evaluation. Not a real insurance policy.",
    )

    usable_width = template.width
    gutter = 8 * mm
    column_width = (usable_width - gutter) / 2

    header_height = 52 * mm
    header = Frame(
        template.leftMargin,
        template.bottomMargin + template.height - header_height,
        usable_width,
        header_height,
        id="header",
    )
    columns = [
        Frame(
            template.leftMargin + index * (column_width + gutter),
            template.bottomMargin,
            column_width,
            template.height - header_height,
            id=f"column{index}",
        )
        for index in range(2)
    ]

    template.addPageTemplates(
        [
            PageTemplate(id="first", frames=[header, *columns]),
            # Later pages are two columns all the way up: only the first page
            # carries the title block.
            PageTemplate(
                id="rest",
                frames=[
                    Frame(
                        template.leftMargin + index * (column_width + gutter),
                        template.bottomMargin,
                        column_width,
                        template.height,
                        id=f"rest{index}",
                    )
                    for index in range(2)
                ],
            ),
        ]
    )

    story = _build_story(doc, st)
    story.insert(0, NextPageTemplate("rest"))
    template.build(story)
    return buffer.getvalue()


def _rasterise(pdf_bytes: bytes, dpi: int = SCAN_DPI) -> bytes:
    """Turn a native-text PDF into an image-only PDF.

    The result has no extractable text layer at all, which is exactly what the
    detector must notice. A light blur and a greyscale conversion approximate an
    office scanner well enough to be a fair test without making the text
    genuinely illegible.
    """
    source = pdfium.PdfDocument(pdf_bytes)
    scale = dpi / 72.0  # pdfium renders in points; 72 points to the inch.

    images: list[Image.Image] = []
    for index in range(len(source)):
        page = source[index]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert("L")
        # Softening simulates the optical blur every scanner introduces. Without
        # it the "scan" is a pixel-perfect render and OCR has an unrealistically
        # easy time.
        image = image.filter(ImageFilter.GaussianBlur(radius=0.4))
        images.append(image)
    source.close()

    if not images:  # pragma: no cover - a document always has pages
        raise RuntimeError("no pages rendered")

    out = io.BytesIO()
    images[0].save(
        out,
        format="PDF",
        save_all=True,
        append_images=images[1:],
        resolution=float(dpi),
        title="Synthetic scanned policy document",
    )
    return out.getvalue()


def generate(output_dir: Path = OUTPUT_DIR, *, which: str = "all") -> list[Path]:
    regular, bold = _register_fonts()
    st = _styles(regular, bold)
    output_dir.mkdir(parents=True, exist_ok=True)

    documents = {
        "demo": ALL_DOCUMENTS,
        "hard": HARD_DOCUMENTS,
        "all": [*ALL_DOCUMENTS, *HARD_DOCUMENTS],
    }[which]

    written: list[Path] = []
    for doc in documents:
        if doc["render"] == "two_column":
            pdf_bytes = _render_two_column(doc, st)
        else:
            pdf_bytes = _render_native(doc, st)
            if doc["render"] == "scanned":
                pdf_bytes = _rasterise(pdf_bytes)

        path = output_dir / f"{doc['slug']}.pdf"
        path.write_bytes(pdf_bytes)
        written.append(path)

        pages = len(pdfium.PdfDocument(pdf_bytes))
        print(
            f"  {doc['slug']:<40} {doc['render']:<8} "
            f"{pages:>2} pages  {len(pdf_bytes) / 1024:>7.1f} KiB"
        )

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Where to write the PDFs (default: eval/golden/samples).",
    )
    parser.add_argument(
        "--set",
        choices=("demo", "hard", "all"),
        default="all",
        help=(
            "demo: the three bundled documents. "
            "hard: the two adversarial ones. "
            "all: both (default)."
        ),
    )
    args = parser.parse_args()

    print(f"Generating sample documents into {args.output_dir}{os.sep}")
    written = generate(args.output_dir, which=args.set)
    print(f"\n{len(written)} documents written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
