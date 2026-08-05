"""Structural interfaces for the ingestion layer.

`typing.Protocol` rather than ABCs: implementations do not inherit from
anything, which keeps the real ones free of framework coupling and makes the
fakes trivial — a fake is any object with the right methods.

Each protocol has at least one real implementation and one fake. The fakes are
not an afterthought: they are what let the chunker, the pipeline and eventually
the whole anti-hallucination layer be tested without a network call or a cent of
spend.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from api.ingest.types import ParsedDocument, TranscribedPage


@runtime_checkable
class DocumentParser(Protocol):
    """Turns PDF bytes into the normalised representation.

    Implementations must not raise on a merely *difficult* document — a page
    that yields nothing is a page with no blocks, not an exception. Raise only
    when the file is not a readable PDF at all.
    """

    name: str

    async def parse(self, data: bytes, *, pages_to_ocr: tuple[int, ...] = ()) -> ParsedDocument:
        """Parse `data`, sending the listed 1-based pages through OCR.

        An empty `pages_to_ocr` means every page has a usable text layer.

        Async because the OCR branch makes network calls. A parser with no OCR
        path is still async — a uniform signature is worth more than saving an
        `await` on the native path.
        """
        ...


@runtime_checkable
class OCRProvider(Protocol):
    """Reads a rendered page image.

    The contract is deliberately narrow — one image in, one `TranscribedPage`
    out — so that swapping a vision model for a classical OCR engine, or for a
    fake, touches nothing else.
    """

    name: str

    async def transcribe(
        self, image_png: bytes, *, hint_lang: str | None = None
    ) -> TranscribedPage:
        """Return the Markdown for one page image, and where its lines sit.

        Implementations must preserve table structure as Markdown tables. They
        must return empty content for a blank page rather than inventing
        plausible text — a hallucinating OCR layer would poison every downstream
        guarantee this system makes, and it would do so invisibly, because there
        is no text layer to check the output against.

        `lines` may be empty. Geometry is an improvement to highlighting;
        Markdown is what the document *is*. An implementation that cannot report
        positions is expected to return the transcription anyway.
        """
        ...
