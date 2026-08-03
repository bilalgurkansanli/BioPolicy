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

from collections.abc import AsyncIterator, Sequence

from api.generation.llm import LLMResponse, ProviderError, Turn
from api.ingest.types import ParsedDocument


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
