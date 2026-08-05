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
from typing import Any, cast

from google.genai import types as genai_types

from api.gemini_client import build_client
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
"""

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 2.0

# Transcription is bounded by what fits on a page. Capping output stops a
# runaway generation from becoming a runaway bill.
MAX_OUTPUT_TOKENS = 4096

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

    async def extract_markdown(self, image_png: bytes, *, hint_lang: str | None = None) -> str:
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
                    return ""
                await asyncio.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

        text = (response.text or "").strip()
        self.pages_processed += 1

        if not text or text == BLANK_SENTINEL:
            return ""

        # Models occasionally wrap the whole transcription in a fence despite
        # being told not to. Strip it rather than letting ``` become content.
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        return text
