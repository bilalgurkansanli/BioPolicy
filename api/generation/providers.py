"""Concrete `LLMProvider` implementations.

## What is verified here, and what is not

Every SDK call below was checked against the installed packages by
introspection — `anthropic` 0.120.2 and `google-genai` 2.16.0 — rather than
recalled. What has **not** happened is a live call: no API key existed when this
was written. So the shapes are right and the semantics are documented, but the
first real request is still the first real request. `api/scripts/list_models.py`
exists to make that first request cheap and informative.

## Model-specific constraints that are easy to get wrong

Claude Haiku 4.5 is not an Opus-tier model and does not share its parameters:

* **`effort` is rejected.** The `output_config.effort` parameter errors on Haiku
  4.5. Nothing here passes it.
* **`temperature` is accepted.** Unlike the newest Opus and Sonnet models, where
  sampling parameters return a 400, Haiku 4.5 still takes `temperature` — and we
  want 0.0, because a grounded-answer system should not be creatively resampling
  its reading of a clause.
* **Max output is 64K, context is 200K.** Both smaller than the 1M/128K of the
  larger models. `MAX_CONTEXT_TOKENS` is set well clear of the 200K figure.

## Structured output

Both providers can enforce the response schema rather than being asked nicely
for JSON in the prompt. That does not make `extract_json` redundant — a provider
without schema support, or a fallback path, still needs it — but on the primary
path a malformed response is now the provider's problem rather than ours.

## Retries

The Anthropic SDK already retries connection errors, 408, 409, 429 and 5xx with
exponential backoff (`max_retries`, default 2). We do **not** add a retry loop
on top: that would multiply the attempts, and a $30 ceiling does not survive
being retried six times per call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import anthropic
from google import genai
from google.genai import types as genai_types

from api.generation.llm import LLMResponse, ProviderError, Turn
from api.logging_config import get_logger

log = get_logger(__name__)


class AnthropicLLM:
    """Primary answering and verification model."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 120.0,
        max_retries: int = 2,
        json_schema: dict[str, object] | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self.model = model
        self.name = "anthropic"
        self._json_schema = json_schema

    def _output_config(self) -> dict[str, Any] | None:
        if self._json_schema is None:
            return None
        # Provider-enforced schema. Note there is no `effort` key here — Haiku
        # 4.5 rejects it.
        return {"format": {"type": "json_schema", "schema": self._json_schema}}

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": t.role, "content": t.content} for t in turns],
            "temperature": temperature,
        }
        output_config = self._output_config()
        if output_config is not None:
            kwargs["output_config"] = output_config

        try:
            message = await self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            # Everything the SDK could not resolve itself. It has already
            # retried the retryable ones.
            raise ProviderError(f"anthropic {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"anthropic connection failed: {exc}") from exc

        # A safety refusal is a successful HTTP 200 with an empty content list.
        # Reading content[0] unconditionally would raise IndexError here.
        if message.stop_reason == "refusal":
            raise ProviderError("anthropic declined the request (stop_reason=refusal)")

        text = "".join(block.text for block in message.content if block.type == "text")
        if message.stop_reason == "max_tokens":
            # Not fatal — the JSON parser will reject a truncated payload and the
            # caller degrades to a refusal — but it is worth seeing in the logs,
            # because it usually means max_tokens is set too tight.
            log.warning("answer_truncated", model=self.model, max_tokens=max_tokens)

        return LLMResponse(
            text=text,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": t.role, "content": t.content} for t in turns],
            "temperature": temperature,
        }
        output_config = self._output_config()
        if output_config is not None:
            kwargs["output_config"] = output_config

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"anthropic {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"anthropic connection failed: {exc}") from exc


class GeminiLLM:
    """Fallback model, and the rewriter.

    The model id is supplied rather than defaulted — ADR 004 forbids guessing
    it, and an empty id means the capability is simply unavailable.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        json_schema: dict[str, object] | None = None,
    ) -> None:
        if not model:
            raise ValueError(
                "GeminiLLM needs an explicit model id. Run "
                "`python -m api.scripts.list_models` to find one; see docs/adr/004."
            )
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.name = "gemini"
        self._json_schema = json_schema

    def _config(self, system: str, max_tokens: int, temperature: float) -> Any:
        config: dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if self._json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = self._json_schema
        return genai_types.GenerateContentConfig(**config)

    @staticmethod
    def _contents(turns: Sequence[Turn]) -> list[Any]:
        # Gemini names the assistant role "model"; sending "assistant" is
        # rejected. This one-word difference is the most common way a
        # multi-turn Gemini call fails.
        return [
            genai_types.Content(
                role="model" if turn.role == "assistant" else "user",
                parts=[genai_types.Part.from_text(text=turn.content)],
            )
            for turn in turns
        ]

    async def complete(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=self._contents(turns),
                config=self._config(system, max_tokens, temperature),
            )
        except Exception as exc:  # the SDK raises a wide range of exception types
            raise ProviderError(f"gemini: {exc}") from exc

        usage = response.usage_metadata
        return LLMResponse(
            text=response.text or "",
            model=self.model,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )

    async def stream(
        self,
        *,
        system: str,
        turns: Sequence[Turn],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=self._contents(turns),
                config=self._config(system, max_tokens, temperature),
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            raise ProviderError(f"gemini: {exc}") from exc
