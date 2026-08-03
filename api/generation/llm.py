"""LLM abstraction, provider failover, and tolerant JSON parsing.

Three things live here, and the third one is the interesting one.

**The protocol.** `LLMProvider` is deliberately small: a system prompt, a list of
turns, a token cap. Anything a specific SDK offers beyond that belongs inside
its own adapter, not in a signature every fake has to implement.

**Failover.** A provider outage should degrade the product, not stop it. The
chain tries each provider in order and returns the first success. It does *not*
retry a provider that returned a bad response — only one that failed to
respond. A model that produced unparseable JSON will produce unparseable JSON
again, and retrying it just spends money twice.

**JSON parsing.** The prompts say "return a single JSON object, nothing else".
Models mostly comply and sometimes do not: a markdown fence, a sentence of
preamble, a trailing "Let me know if you need anything else." Being strict here
would convert a cosmetic deviation into a failed answer, so the parser is
tolerant about the wrapper and strict about the content.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from api.logging_config import get_logger

log = get_logger(__name__)

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class Turn:
    role: Role
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One billable call, ready to be written to `usage_events`.

    Token counts come from the provider's own response, never from a local
    tokenizer. The tokenizer used for chunk budgeting is a different vendor's
    and is only a yardstick; the budget circuit breaker has to be fed real
    numbers or it is measuring something other than the bill.
    """

    operation: str  # 'answer' | 'verify' | 'rewrite' | 'embed' | 'ocr'
    model: str
    input_tokens: int
    output_tokens: int

    @classmethod
    def from_response(cls, operation: str, response: LLMResponse) -> UsageRecord:
        return cls(
            operation=operation,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )


class ProviderError(RuntimeError):
    """The provider failed to produce a response. Failover-eligible."""


class AllProvidersFailedError(RuntimeError):
    """Every provider in the chain failed."""


@runtime_checkable
class LLMProvider(Protocol):
    # Read-only properties rather than settable attributes: an implementation
    # may expose these as plain class attributes (the fakes do) or compute them
    # (FailoverLLM delegates to its primary). Declaring them settable would
    # exclude the second case for no benefit — nothing ever assigns to them.
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse: ...

    def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]: ...


@dataclass(slots=True)
class FailoverLLM:
    """Tries each provider in order; returns the first that responds.

    Only `ProviderError` triggers failover. A provider that responded with
    something we could not use has done its job — the fault is downstream, and
    asking a second model the same question would spend money to get the same
    class of answer.
    """

    providers: list[LLMProvider]
    attempted: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.providers:
            raise ValueError("FailoverLLM needs at least one provider")

    @property
    def name(self) -> str:
        return self.providers[0].name

    @property
    def model(self) -> str:
        return self.providers[0].model

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.attempted = []
        errors: list[str] = []

        for provider in self.providers:
            self.attempted.append(provider.name)
            try:
                return await provider.complete(
                    system=system, turns=turns, max_tokens=max_tokens, temperature=temperature
                )
            except ProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
                log.warning(
                    "provider_failed",
                    provider=provider.name,
                    error=str(exc),
                    remaining=len(self.providers) - len(self.attempted),
                )

        raise AllProvidersFailedError("; ".join(errors))

    async def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        """Stream from the first provider that starts producing tokens.

        Failover only applies **before the first token**. Once text has reached
        the user, switching providers would append a second, differently-worded
        answer onto the first — so a mid-stream failure is re-raised and the
        client shows an error on a partial response. That is the honest
        outcome; silently continuing with another model would produce a reply no
        single model actually wrote.
        """
        self.attempted = []
        errors: list[str] = []

        for provider in self.providers:
            self.attempted.append(provider.name)
            emitted = False
            try:
                async for token in provider.stream(
                    system=system, turns=turns, max_tokens=max_tokens, temperature=temperature
                ):
                    emitted = True
                    yield token
                return
            except ProviderError as exc:
                if emitted:
                    raise
                errors.append(f"{provider.name}: {exc}")
                log.warning("provider_stream_failed", provider=provider.name, error=str(exc))

        raise AllProvidersFailedError("; ".join(errors))


# -----------------------------------------------------------------------------
# tolerant JSON extraction
# -----------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE)


class MalformedResponseError(ValueError):
    """The model's output could not be read as the JSON object we asked for."""


def extract_json(text: str) -> dict[str, object]:
    """Pull a single JSON object out of a model response.

    Handles, in order: a clean object; an object inside a markdown fence; an
    object embedded in prose. Anything else raises.
    """
    candidates: list[str] = []

    stripped = text.strip()
    if stripped:
        candidates.append(stripped)

    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())

    # Last resort: the outermost balanced braces. `json.loads` will reject the
    # slice if the braces were not really an object, so this cannot silently
    # produce nonsense.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise MalformedResponseError(
        f"No JSON object found in a {len(text)}-character response beginning {text[:80]!r}"
    )
