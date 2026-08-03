"""Native-text vs scanned classification.

This runs before anything expensive and decides how much the document will cost
to ingest. Getting it wrong is expensive in both directions: classifying a
native document as scanned burns vision-model tokens on pages that already have
perfectly good text, and classifying a scan as native produces a document with
no content and no error.

pypdfium2 is used rather than pdfplumber because this is a fast pre-pass over
every page — pdfium reads the text layer in C, where pdfminer builds a Python
object per character.
"""

from __future__ import annotations

import pypdfium2 as pdfium

from api.constants import (
    MIN_CHARS_FOR_TEXT_LAYER,
    NATIVE_TEXT_RATIO,
    SCANNED_TEXT_RATIO,
)
from api.ingest.types import DetectionResult, PageTextStats, SourceType
from api.logging_config import get_logger

log = get_logger(__name__)


class NotAPdfError(ValueError):
    """The bytes are not a PDF we can open."""


def detect(data: bytes) -> DetectionResult:
    """Classify a document as native, scanned, or mixed.

    Raises `NotAPdfError` if the bytes cannot be opened. Never raises for a
    document that is merely empty or difficult.
    """
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise NotAPdfError(str(exc)) from exc

    try:
        stats: list[PageTextStats] = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            # WHY strip() and a threshold rather than `if text`: scanned PDFs
            # very often carry a handful of stray characters — a header stamp, a
            # form field, a scanner watermark, an empty text object. A bare
            # truthiness check would classify those pages as native and skip OCR
            # on a page that is, to a reader, entirely blank.
            char_count = len(text.strip())
            stats.append(
                PageTextStats(
                    number=index + 1,
                    char_count=char_count,
                    has_text_layer=char_count >= MIN_CHARS_FOR_TEXT_LAYER,
                )
            )
    finally:
        document.close()

    page_count = len(stats)
    if page_count == 0:
        raise NotAPdfError("PDF contains no pages")

    with_text = sum(1 for p in stats if p.has_text_layer)
    ratio = with_text / page_count

    source_type: SourceType
    if ratio > NATIVE_TEXT_RATIO:
        source_type = "native"
    elif ratio < SCANNED_TEXT_RATIO:
        source_type = "scanned"
    else:
        source_type = "mixed"

    log.info(
        "document_detected",
        source_type=source_type,
        page_count=page_count,
        pages_with_text=with_text,
        text_layer_ratio=round(ratio, 3),
    )

    return DetectionResult(
        source_type=source_type,
        page_count=page_count,
        text_layer_ratio=ratio,
        pages=tuple(stats),
    )


def page_count(data: bytes) -> int:
    """Page count alone, for upload validation before anything else runs."""
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise NotAPdfError(str(exc)) from exc
    try:
        return len(document)
    finally:
        document.close()
