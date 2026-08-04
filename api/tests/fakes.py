"""Fake implementations of every provider protocol.

These exist so that the pipeline, the chunker and eventually the whole
anti-hallucination layer can be tested without a network call or a cent of
spend. They are part of the design, not test scaffolding bolted on afterwards —
the protocols in `api/ingest/protocols.py` are shaped the way they are partly to
make these possible.

A fake here is deliberately *dumb*. It returns fixed or trivially-derived
output. A fake that tries to be clever ends up encoding the same assumptions as
the code under test, and then the test passes for the wrong reason.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import UUID

from api.constants import EMBEDDING_DIM
from api.generation.llm import LLMResponse, ProviderError, Turn
from api.ingest.types import ParsedDocument
from api.retrieval.types import RetrievedChunk
from api.storage import StoredObject


class FakeOCRProvider:
    """Returns canned Markdown, and records what it was asked to read.

    `calls` lets a test assert the thing that actually costs money: how many
    page images were sent. A regression that OCRs pages which already have a
    text layer is a cost bug, not a correctness bug, and it would otherwise be
    invisible.
    """

    name = "fake-ocr"

    def __init__(self, markdown: str | None = None) -> None:
        self.markdown = markdown if markdown is not None else _DEFAULT_MARKDOWN
        self.calls: list[int] = []  # byte length of each image received

    async def extract_markdown(self, image_png: bytes, *, hint_lang: str | None = None) -> str:
        self.calls.append(len(image_png))
        return self.markdown

    @property
    def call_count(self) -> int:
        return len(self.calls)


class BlankOCRProvider:
    """Returns nothing, always.

    Models the honest behaviour required by the `OCRProvider` contract for a
    blank page: return an empty string rather than inventing plausible content.
    """

    name = "blank-ocr"

    def __init__(self) -> None:
        self.call_count = 0

    async def extract_markdown(self, image_png: bytes, *, hint_lang: str | None = None) -> str:
        self.call_count += 1
        return ""


class StaticParser:
    """A `DocumentParser` that ignores its input and returns a prepared document."""

    name = "static-parser"

    def __init__(self, document: ParsedDocument) -> None:
        self._document = document
        self.call_count = 0

    async def parse(self, data: bytes, *, pages_to_ocr: tuple[int, ...] = ()) -> ParsedDocument:
        self.call_count += 1
        return self._document


class ScriptedLLM:
    """Returns prepared responses in order and records every call.

    `systems` and `payloads` are what the verifier tests assert against: the
    pass is only meaningful if the user's question genuinely never reaches it,
    and the only way to check that is to inspect what was actually sent.
    """

    name = "scripted"
    model = "scripted-model"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.systems: list[str] = []
        self.payloads: list[str] = []
        self.call_count = 0

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.call_count += 1
        self.systems.append(system)
        self.payloads.append("\n".join(t.content for t in turns))

        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of prepared responses")
        text = self._responses.pop(0)
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=len(system) // 4,
            output_tokens=len(text) // 4,
        )

    async def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        response = await self.complete(
            system=system, turns=turns, max_tokens=max_tokens, temperature=temperature
        )
        for word in response.text.split(" "):
            yield word + " "


class SlowLLM:
    """Never answers in time. Models a stalled provider, not a failing one.

    An outage raises; this does not, which is the harder case — nothing signals
    that anything is wrong, and without a ceiling the caller simply waits.
    """

    name = "slow"
    model = "slow-model"

    def __init__(self, delay_seconds: float = 60.0) -> None:
        self.delay_seconds = delay_seconds
        self.call_count = 0

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.call_count += 1
        await asyncio.sleep(self.delay_seconds)
        raise AssertionError("SlowLLM should never be waited out")

    async def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        await self.complete(
            system=system, turns=turns, max_tokens=max_tokens, temperature=temperature
        )
        yield ""  # pragma: no cover - unreachable, keeps this an async generator


class FailingLLM:
    """Always raises `ProviderError`. Models an outage, not a bad answer."""

    def __init__(self, name: str = "failing", message: str = "upstream unavailable") -> None:
        self.name = name
        self.model = f"{name}-model"
        self.message = message
        self.call_count = 0

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.call_count += 1
        raise ProviderError(self.message)

    async def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        self.call_count += 1
        # The empty loop is what makes this an async *generator* rather than a
        # coroutine returning one. Without it, `async for` over the result would
        # fail with a TypeError instead of the ProviderError the failover logic
        # is meant to catch — and the test would pass for the wrong reason.
        for _ in ():
            yield ""
        raise ProviderError(self.message)


class StubEmbedder:
    """Deterministic vectors of the correct width.

    The values are meaningless — the retriever never inspects them, it only
    hands them to the store. What matters for testing is that the *width* is
    right and that document and query paths are recorded separately, so a test
    can catch the two being swapped.
    """

    name = "stub-embedder"
    model = "stub-embedding-model"

    def __init__(self, dimensions: int = EMBEDDING_DIM) -> None:
        self.dimensions = dimensions
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def _vector(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text) or 1
        return [((seed * (i + 1)) % 1000) / 1000.0 for i in range(self.dimensions)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self._vector(text)


class StubStore:
    """Returns prepared search results and records how it was queried."""

    def __init__(self, results: list[RetrievedChunk] | None = None) -> None:
        self.results = results or []
        self.queries: list[str] = []
        self.embeddings: list[list[float]] = []
        self.accessors: list[UUID | None] = []

    async def hybrid_search(
        self,
        *,
        document_id: UUID,
        user_id: UUID | None,
        query_embedding: list[float],
        query_text: str,
        vector_limit: int = 30,
        keyword_limit: int = 30,
    ) -> list[RetrievedChunk]:
        self.queries.append(query_text)
        self.embeddings.append(query_embedding)
        self.accessors.append(user_id)
        return list(self.results)


_DEFAULT_MARKDOWN = """# Madde 1 — Teminat Kapsamı

Bu poliçe, anlaşmalı kurumlarda SGK tarafından karşılanmayan fark ücretlerini
karşılar.

| Teminat | Limit | Katılım Payı |
| --- | --- | --- |
| Yatarak Tedavi | Limitsiz | Yok |
| Ayakta Tedavi (muayene) | Yılda 8 kez | %20 |

## Madde 2 — Bekleme Süreleri

Doğum teminatı için bekleme süresi on iki aydır.
"""


# -----------------------------------------------------------------------------
# database and storage
# -----------------------------------------------------------------------------


class FakeConnection:
    """Records statements. Deliberately understands no SQL.

    The safety-layer tests are about *ordering and conditions* — did the file go
    before the rows, was the audit entry written only when both halves worked —
    not about what the SQL means. A fake that parsed SQL would be re-encoding the
    queries it is meant to check.
    """

    def __init__(self, log: list[tuple[str, tuple[object, ...]]]) -> None:
        self.log = log
        self.fetchval_result: object = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        self.log.append(("begin", ()))
        yield
        self.log.append(("commit", ()))

    async def execute(self, query: str, *args: object) -> None:
        self.log.append((_first_words(query), args))

    async def fetchval(self, query: str, *args: object) -> object:
        self.log.append((_first_words(query), args))
        return self.fetchval_result


class FakePool:
    """An asyncpg pool that returns prepared rows and remembers every query."""

    def __init__(
        self,
        *,
        fetch: Sequence[Sequence[dict[str, object]]] = (),
        fetchrow: Sequence[dict[str, object] | None] = (),
        fetchval: object = 0,
    ) -> None:
        self._fetch = list(fetch)
        self._fetchrow = list(fetchrow)
        self.fetchval_result = fetchval
        self.log: list[tuple[str, tuple[object, ...]]] = []
        self.queries: list[str] = []

    @property
    def statements(self) -> list[str]:
        """Just the operation names, in order. What ordering assertions read."""
        return [name for name, _ in self.log]

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.queries.append(query)
        self.log.append((_first_words(query), args))
        return list(self._fetch.pop(0)) if self._fetch else []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.queries.append(query)
        self.log.append((_first_words(query), args))
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def execute(self, query: str, *args: object) -> None:
        self.queries.append(query)
        self.log.append((_first_words(query), args))

    async def executemany(self, query: str, args: Sequence[Sequence[object]]) -> None:
        self.queries.append(query)
        self.log.append((_first_words(query), tuple(args)))

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[FakeConnection]:
        connection = FakeConnection(self.log)
        connection.fetchval_result = self.fetchval_result
        yield connection


def _first_words(query: str) -> str:
    return " ".join(query.strip().split()[:2]).lower()


class FakeStorage:
    """Object storage that can be told to fail, which is the interesting case."""

    def __init__(self, *, removable: bool = True, size: int | None = 1024) -> None:
        self.removable = removable
        self.size = size
        self.removed: list[str] = []
        self.log: list[tuple[str, tuple[object, ...]]] = []

    def share_log(self, log: list[tuple[str, tuple[object, ...]]]) -> None:
        """Write into the pool's log so call *ordering* across both is visible."""
        self.log = log

    async def remove(self, path: str) -> bool:
        self.log.append(("storage.remove", (path,)))
        if not self.removable:
            return False
        self.removed.append(path)
        return True

    async def stat(self, path: str) -> object:
        self.log.append(("storage.stat", (path,)))
        if self.size is None:
            return None
        return StoredObject(path=path, byte_size=self.size)

    async def download(self, path: str) -> bytes:
        self.log.append(("storage.download", (path,)))
        return b"%PDF-1.4 fake"
