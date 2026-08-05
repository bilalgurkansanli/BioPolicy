"""Vision OCR via Gemini.

The `OCRProvider` contract has one clause that matters more than the rest: an
unreadable or blank page must return an **empty string**, never invented
content. A hallucinating OCR layer would poison every guarantee downstream and
do it invisibly — citation binding checks a quote against the chunk, and if the
chunk itself is fabricated the check passes. There is no text layer to compare
against on a scanned page, so this is the one place in the pipeline where a
confabulation cannot be caught later. The prompt therefore spends most of its
length on that instruction, and the response is filtered for the refusal
sentinel before it is returned.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from google.genai import types as genai_types

from api.gemini_client import build_client
from api.ingest.types import BBox, OcrLine, TranscribedPage
from api.logging_config import get_logger

log = get_logger(__name__)

# The model emits this alone when a page carries no readable text. Checked for
# exactly, so a page that genuinely discusses blankness is not discarded.
BLANK_SENTINEL = "[[BLANK_PAGE]]"

OCR_PROMPT = f"""Transcribe this page of a document into Markdown.

Rules, in order of importance:

1. Transcribe only what is actually visible. Never infer, complete, correct or
   invent text. If a word is illegible, write [?] rather than guessing what it
   probably says. A gap is recoverable; a plausible invention is not.
2. If the page contains no readable text at all — blank, or too degraded to
   read — reply with exactly {BLANK_SENTINEL} and nothing else.
3. Preserve tables as Markdown tables. Keep every row and column aligned as it
   appears. In an insurance policy the coverage table is usually the most
   important thing on the page; a figure moved into the wrong row is worse than
   no table at all.
4. Copy numbers exactly as printed, including thousands separators and currency
   symbols: 1.800.000 stays 1.800.000.
5. Use # and ## for headings that are visually headings.
6. Do not add commentary, do not summarise, do not explain what the page is.
   Output only the transcription.

Alongside the Markdown, report where each line you read sits on the page.

A "line" is one visual row of text. In a table, every cell is its own line — a
coverage row that comes back as a single box cannot be highlighted cell by cell.
Give each line its text exactly as printed and its bounding box as
[ymin, xmin, ymax, xmax], normalised to 0-1000 over the whole image.

The Markdown is the primary output. The positions describe what you have
already read; they must never change what you transcribe.
"""

# WHY one call and not two: transcription is the expensive stage of ingestion,
# and doubling it to fetch geometry would be paid on every scanned page forever.
# Measured on the sample before committing to it — the coverage table, every
# figure in it and the article headings came back identical to the
# Markdown-only call. The prompt names the primary output for the same reason.
#
# If it ever does degrade, the fix is to split the calls, not to drop the
# transcription: a wrong transcription is a wrong answer, while a missing box is
# only a coarser highlight.

TRANSCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "markdown": {"type": "string"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "box_2d": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["text", "box_2d"],
            },
        },
    },
    "required": ["markdown", "lines"],
}

# The model is asked for 0-1000. Anything outside that is a misunderstanding
# rather than a page extending past its own edge.
BOX_SCALE = 1000.0

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 2.0

# Transcription is bounded by what fits on a page. Capping output stops a
# runaway generation from becoming a runaway bill.
# Raised for the geometry: a dense page runs to ~55 lines, and each one costs
# a short JSON object on top of its own text.
MAX_OUTPUT_TOKENS = 12288

# One call transcribes a whole rendered page and is measured in tens of seconds,
# so the query-time ceiling would cut off healthy work. Ingestion is
# asynchronous (ADR 007): a slow page delays a document, not a waiting user.
OCR_TIMEOUT_SECONDS = 180.0


class GeminiOCR:
    name = "gemini-vision"

    def __init__(self, api_key: str, model: str) -> None:
        if not model:
            raise ValueError(
                "GeminiOCR needs an explicit model id. Run "
                "`python -m api.scripts.list_models` to find one; see docs/adr/004."
            )
        self._client = build_client(api_key, timeout_seconds=OCR_TIMEOUT_SECONDS)
        self._model = model
        self.pages_processed = 0

    async def transcribe(
        self, image_png: bytes, *, hint_lang: str | None = None
    ) -> TranscribedPage:
        prompt = OCR_PROMPT
        if hint_lang:
            prompt += f"\nThe document is written in {hint_lang}.\n"

        contents = [
            genai_types.Part.from_bytes(data=image_png, mime_type="image/png"),
            genai_types.Part.from_text(text=prompt),
        ]
        config = genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=TRANSCRIPTION_SCHEMA,
        )

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model, contents=cast(Any, contents), config=config
                )
                break
            except Exception as exc:  # the SDK raises broadly
                if attempt == MAX_ATTEMPTS:
                    log.error("ocr_failed", attempts=MAX_ATTEMPTS, error=str(exc))
                    # An OCR failure is a page we could not read, not a document
                    # we should invent. Returning empty keeps the honest
                    # contract; the pipeline reports fewer pages parsed.
                    return TranscribedPage(markdown="")
                await asyncio.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

        self.pages_processed += 1

        try:
            payload = json.loads(response.text or "{}")
        except json.JSONDecodeError as exc:
            log.error("ocr_unreadable", error=str(exc))
            return TranscribedPage(markdown="")

        text = str(payload.get("markdown") or "").strip()
        if not text or text == BLANK_SENTINEL:
            return TranscribedPage(markdown="")

        # Models occasionally wrap the whole transcription in a fence despite
        # being told not to. Strip it rather than letting ``` become content.
        if text.startswith("```"):
            fenced = text.splitlines()
            if fenced[0].startswith("```"):
                fenced = fenced[1:]
            if fenced and fenced[-1].strip() == "```":
                fenced = fenced[:-1]
            text = "\n".join(fenced).strip()

        lines = _lines_from(payload.get("lines"))
        log.info("ocr_page", characters=len(text), lines=len(lines))
        return TranscribedPage(markdown=text, lines=lines)


def _lines_from(raw: Any) -> tuple[OcrLine, ...]:
    """Turn the model's boxes into fractional `OcrLine`s, dropping the nonsense.

    Geometry is optional, so anything malformed is discarded silently rather
    than failing the page: losing a box costs a precise highlight, losing the
    page costs the document.
    """
    if not isinstance(raw, list):
        return ()

    lines: list[OcrLine] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        box = entry.get("box_2d")
        if not text or not isinstance(box, list) or len(box) != 4:
            continue
        try:
            ymin, xmin, ymax, xmax = (float(value) / BOX_SCALE for value in box)
        except (TypeError, ValueError):
            continue
        # A zero-area or inverted box points at nothing, and a box outside the
        # page is the model having lost the coordinate system.
        if not (0.0 <= xmin < xmax <= 1.0 and 0.0 <= ymin < ymax <= 1.0):
            continue
        lines.append(OcrLine(text=text, bbox=BBox(x0=xmin, top=ymin, x1=xmax, bottom=ymax)))

    return tuple(lines)
