"""Who pays for what, when something goes wrong.

Three separate paths in this system decide whether an allowance is spent or
handed back, and each of them had the same shape of bug: a refusal that costs
the sender nothing is a refusal they can repeat for free.

The rule these pin down is one sentence. **A slot comes back when the failure
was ours, and stays spent when the input was the problem.**
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from api.documents import DocumentRecord
from api.ingest.pipeline import IngestionError, IngestionPipeline

DOCUMENT, USER = uuid4(), uuid4()


class _Documents:
    def __init__(self) -> None:
        self.failed: list[str] = []

    async def mark_failed(self, document_id: object, message: str) -> None:
        self.failed.append(message)


def _pipeline(exc: Exception) -> tuple[IngestionPipeline, _Documents]:
    documents = _Documents()
    pipeline = IngestionPipeline.__new__(IngestionPipeline)
    pipeline._documents = documents  # type: ignore[assignment]

    async def run(_document: object, _data: bytes) -> None:
        raise exc

    pipeline.run = run  # type: ignore[assignment, method-assign]
    return pipeline, documents


def _record() -> DocumentRecord:
    return DocumentRecord(
        id=DOCUMENT,
        user_id=USER,
        filename="policy.pdf",
        storage_path=f"uploads/{USER}/{DOCUMENT}.pdf",
        byte_size=1024,
        status="parsing",
        is_sample=False,
        attempts=1,
    )


async def _blame(exc: Exception) -> list[bool]:
    """Run one failing ingest and report what it told the caller about blame."""
    pipeline, _ = _pipeline(exc)
    seen: list[bool] = []

    async def on_failure(blame_input: bool) -> None:
        seen.append(blame_input)

    assert await pipeline.run_safely(_record(), b"", on_failure=on_failure) is None
    return seen


async def test_a_file_that_is_not_a_pdf_keeps_the_slot_it_spent() -> None:
    """The hole this closes.

    Every ingestion failure used to refund, so a file that could never work
    could be re-sent forever — 25MB of storage and a worker slot per attempt, at
    no cost to the sender.
    """
    assert await _blame(IngestionError("not a pdf", blame_input=True)) == [True]


async def test_a_failure_on_our_side_gives_the_slot_back() -> None:
    """The case the refund was built for, and it still holds.

    The first real policy anyone uploaded died on an embedding quota we were
    exceeding. Nothing was rendered, so nothing is owed.
    """
    assert await _blame(IngestionError("embedding provider unavailable")) == [False]


async def test_an_unexpected_crash_is_always_ours() -> None:
    """A bug here is not something to charge somebody for, whatever provoked it."""
    assert await _blame(RuntimeError("boom")) == [False]


@pytest.mark.parametrize(
    "message",
    [
        "This file could not be opened as a PDF",
        "This document has 400 pages",
        "This scanned document needs text recognition on 90 pages",
    ],
)
async def test_published_limits_are_refusals_rather_than_failures(message: str) -> None:
    """All three are decided from the file alone, before any work is done.

    Grouped deliberately: they are the same judgement, and refunding any one of
    them reopens the same free-retry loop.
    """
    assert await _blame(IngestionError(message, blame_input=True)) == [True]
