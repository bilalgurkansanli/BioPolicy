"""Ingestion orchestration: detect → parse → chunk → embed → store.

## Failures are user-safe by construction

Every exception that escapes a stage is caught here, logged in full server-side,
and turned into a short sentence a person can act on. Nothing from the exception
reaches `documents.error_message`, because that column is returned by
`GET /documents/{id}` and lands in a browser. A stack trace there leaks file
paths, library versions, and occasionally a connection string.

The mapping from cause to sentence is deliberate rather than generic: "this PDF
is password-protected" tells the user what to do; "ingestion failed" does not.

## The pipeline is re-runnable

ADR 007 makes ingestion retryable, which means a stage may run twice on the same
document. `replace_chunks` deletes before it inserts, inside one transaction, so
a retry cannot produce duplicates. Duplicated chunks would be worse than missing
ones: they crowd out other content in retrieval while adding nothing.

## Cost is bounded before work starts, not during

The OCR page cap is checked against the *detected* page count before a single
image is rendered. Discovering the limit halfway through means having already
paid for half a document (ADR 005).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from api.config import get_settings
from api.constants import (
    STATUS_CHUNKING,
    STATUS_EMBEDDING,
    STATUS_OCR,
    STATUS_PARSING,
)
from api.documents import DocumentRecord, DocumentRepository
from api.ingest.chunker import Chunker
from api.ingest.detector import NotAPdfError, detect
from api.ingest.injection import scan as scan_for_injection
from api.ingest.protocols import DocumentParser
from api.ingest.types import ParsedDocument
from api.logging_config import get_logger
from api.retrieval.embedder import EmbeddingError, EmbeddingProvider
from api.retrieval.gemini_embedder import is_daily_quota
from api.retrieval.store import ChunkStore

log = get_logger(__name__)


class IngestionError(Exception):
    """Carries a message that is safe to show a user.

    `blame_input` says whose fault the failure was, and it decides whether the
    uploader gets their daily slot back.

    The default is `False` — ours — because that is the case the refund exists
    for: the first real policy anyone uploaded died on an embedding quota we
    were exceeding, and the row it left behind spent their one document for the
    day. Nothing was rendered, so nothing was owed.

    The reverse is a hole. A file that is not a PDF fails the same way, gets the
    same refund, and can be re-sent forever — 25MB of storage and a worker slot
    per attempt, at no cost to the sender. Set this where the bytes themselves
    are the problem: the sender chose them, and choosing badly is not something
    the service should absorb without limit.
    """

    def __init__(self, user_message: str, *, cause: str = "", blame_input: bool = False) -> None:
        super().__init__(cause or user_message)
        self.user_message = user_message
        self.blame_input = blame_input


@dataclass(slots=True)
class IngestionResult:
    document_id: UUID
    page_count: int
    source_type: str
    chunk_count: int
    table_chunks: int
    ocr_pages: int
    duration_seconds: float


class IngestionPipeline:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        store: ChunkStore,
        parser: DocumentParser,
        embedder: EmbeddingProvider,
        chunker: Chunker | None = None,
    ) -> None:
        self._documents = documents
        self._store = store
        self._parser = parser
        self._embedder = embedder
        self._chunker = chunker or Chunker()

    async def run(self, document: DocumentRecord, data: bytes) -> IngestionResult:
        """Ingest one document. Raises `IngestionError` with a safe message."""
        started = time.monotonic()
        settings = get_settings()

        # --- detect ---------------------------------------------------------
        await self._documents.set_status(document.id, STATUS_PARSING)
        try:
            detection = detect(data)
        except NotAPdfError as exc:
            raise IngestionError(
                "This file could not be opened as a PDF. It may be corrupted, "
                "password-protected, or not actually a PDF.",
                cause=str(exc),
                blame_input=True,
            ) from exc

        if detection.page_count > settings.max_page_count:
            raise IngestionError(
                f"This document has {detection.page_count} pages. The limit is "
                f"{settings.max_page_count}.",
                blame_input=True,
            )

        ocr_pages = detection.pages_needing_ocr
        if ocr_pages:
            # ADR 005: the cap binds before any page image is rendered.
            if len(ocr_pages) > settings.max_ocr_page_count:
                raise IngestionError(
                    f"This scanned document needs text recognition on "
                    f"{len(ocr_pages)} pages, and the limit is "
                    f"{settings.max_ocr_page_count}. Scanned documents are far more "
                    f"expensive to process than ones with a text layer.",
                    # A published limit the file does not meet, decided before
                    # any page was rendered. Like the two above, this is a
                    # refusal rather than a failure, and refusals are not
                    # refundable — otherwise they are free to repeat.
                    blame_input=True,
                )
            await self._documents.set_status(document.id, STATUS_OCR)

        # --- parse ----------------------------------------------------------
        try:
            parsed = await self._parser.parse(data, pages_to_ocr=ocr_pages)
        except RuntimeError as exc:
            # Raised when a scan arrives with no OCR provider configured.
            raise IngestionError(
                "This document appears to be scanned, and text recognition is not "
                "available right now.",
                cause=str(exc),
            ) from exc
        except Exception as exc:
            raise IngestionError(
                "This document could not be read. It may use an unusual encoding or be damaged.",
                cause=f"{type(exc).__name__}: {exc}",
            ) from exc

        parsed.source_type = detection.source_type
        parsed.detected_lang = detect_language(parsed)

        # Scan the extracted text, not the raw bytes: what matters is what the
        # retrieval layer will later put in front of a model, and that is what
        # parsing produced. Text in the PDF that no parser extracts cannot reach
        # the prompt either, so it is not this scan's problem.
        #
        # Runs here rather than at upload because a scanned document has no text
        # until OCR has finished, and warning only the users whose PDFs happen to
        # have a text layer would be worse than not warning anyone.
        findings = [
            {"rule": f.rule, "why": f.why, "excerpt": f.excerpt}
            for f in scan_for_injection(parsed.full_text)
        ]
        if findings:
            log.info(
                "injection_text_found",
                document_id=str(document.id),
                rules=[f["rule"] for f in findings],
            )

        await self._documents.set_metadata(
            document.id,
            page_count=detection.page_count,
            source_type=detection.source_type,
            detected_lang=parsed.detected_lang,
            injection_findings=findings,
        )

        # --- chunk ----------------------------------------------------------
        await self._documents.set_status(document.id, STATUS_CHUNKING)
        chunks = self._chunker.chunk(parsed)
        if not chunks:
            # An empty document is a real outcome, not a crash — but storing it
            # as `ready` would produce a document that silently refuses every
            # question, which looks like a bug in the answering layer.
            raise IngestionError(
                "No readable text was found in this document. If it is a scan, it "
                "may be too low-quality to process."
            )

        # --- embed ----------------------------------------------------------
        await self._documents.set_status(document.id, STATUS_EMBEDDING)
        try:
            embeddings = await self._embedder.embed_documents([c.embed_text for c in chunks])
        except EmbeddingError as exc:
            # Two different ceilings, two different pieces of advice. The
            # per-minute one clears by itself; the daily one does not clear
            # until tomorrow, and "try again in a few minutes" sends somebody
            # into a retry loop that cannot succeed.
            raise IngestionError(
                (
                    "The daily processing allowance for this demo has been used up. "
                    "Please try again tomorrow."
                )
                if is_daily_quota(exc)
                else (
                    "This document could not be prepared for search. Please try "
                    "again in a few minutes."
                ),
                cause=str(exc),
            ) from exc

        # --- store ----------------------------------------------------------
        await self._store.replace_chunks(
            document_id=document.id,
            user_id=document.user_id,
            chunks=chunks,
            embeddings=embeddings,
        )
        # Only OCR'd pages produce these. Called unconditionally so that a
        # re-ingest which no longer needs OCR clears the previous run's boxes
        # rather than leaving them to be drawn over a page that now has real
        # text underneath.
        await self._store.replace_page_lines(
            document_id=document.id,
            user_id=document.user_id,
            lines_by_page=parsed.ocr_lines,
        )
        await self._documents.mark_ready(document.id)

        result = IngestionResult(
            document_id=document.id,
            page_count=detection.page_count,
            source_type=detection.source_type,
            chunk_count=len(chunks),
            table_chunks=sum(1 for c in chunks if c.content_type == "table"),
            ocr_pages=len(ocr_pages),
            duration_seconds=round(time.monotonic() - started, 2),
        )
        log.info(
            "ingestion_complete",
            document_id=str(document.id),
            pages=result.page_count,
            source_type=result.source_type,
            chunks=result.chunk_count,
            tables=result.table_chunks,
            seconds=result.duration_seconds,
        )
        return result

    async def run_safely(
        self,
        document: DocumentRecord,
        data: bytes,
        *,
        on_failure: Callable[[bool], Awaitable[None]] | None = None,
    ) -> IngestionResult | None:
        """Run, converting any failure into a `failed` status.

        The background task calls this. It never raises, because an exception
        escaping a fire-and-forget task is swallowed by the event loop and the
        document sits in `parsing` forever.

        `on_failure` is awaited with `blame_input` — whether the bytes the
        uploader sent were the problem. The caller uses it to decide the refund,
        because "nothing was rendered" and "nothing is owed" are only the same
        sentence when the failure was ours. A crash is always ours: an
        unexpected exception is a bug here, whatever provoked it.
        """
        try:
            return await self.run(document, data)
        except IngestionError as exc:
            log.error(
                "ingestion_failed",
                document_id=str(document.id),
                user_message=exc.user_message,
                cause=str(exc),
                blame_input=exc.blame_input,
            )
            await self._documents.mark_failed(document.id, exc.user_message)
            if on_failure is not None:
                await on_failure(exc.blame_input)
            return None
        except Exception as exc:
            log.error(
                "ingestion_crashed",
                document_id=str(document.id),
                exc_info=exc,
            )
            await self._documents.mark_failed(
                document.id,
                "Something went wrong while processing this document. Please try again.",
            )
            if on_failure is not None:
                await on_failure(False)
            return None


# -----------------------------------------------------------------------------
# language detection
# -----------------------------------------------------------------------------

# Function words, not content words. A Turkish policy is full of words a naive
# detector would score as "insurance vocabulary" in either language; these are
# grammatical and appear in any Turkish prose regardless of subject.
_TURKISH_MARKERS = frozenset(
    {
        "ve",
        "ile",
        "bu",
        "için",
        "olan",
        "veya",
        "ancak",
        "halinde",
        "üzere",
        "gibi",
        "daha",
        "kadar",
        "sonra",
        "tarafından",
    }
)
_ENGLISH_MARKERS = frozenset(
    {
        "the",
        "and",
        "of",
        "to",
        "in",
        "for",
        "shall",
        "any",
        "which",
        "with",
        "that",
        "under",
        "such",
        "from",
    }
)

# Characters that exist in Turkish and not in English. Strong evidence on their
# own, so they are weighted more heavily than a single function word.
_TURKISH_CHARS = frozenset("çğıöşüÇĞİÖŞÜ")
_CHAR_WEIGHT = 3


def detect_language(document: ParsedDocument) -> str:
    """Return 'tr' or 'en'.

    Deliberately a heuristic rather than a dependency. This picks the FTS
    configuration for keyword search and the default reply language; it is not
    load-bearing enough to justify a model or another package, and it degrades
    gracefully — a wrong guess costs some keyword-arm quality, not correctness,
    because the vector arm is language-agnostic and the user's own question
    decides the reply language anyway.
    """
    text = " ".join(b.text for b in document.blocks[:60]).casefold()
    if not text.strip():
        return "en"

    words = set(text.split())
    turkish = len(words & _TURKISH_MARKERS)
    english = len(words & _ENGLISH_MARKERS)

    if any(ch in _TURKISH_CHARS for ch in text):
        turkish += _CHAR_WEIGHT

    return "tr" if turkish > english else "en"
