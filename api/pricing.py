"""Token pricing, for the budget circuit breaker.

## Where these numbers come from

Anthropic's rates are **verified**, not recalled: Claude Haiku 4.5 is
$1.00 per million input tokens and $5.00 per million output tokens, checked on
2026-08-04. Its context window is 200K and its maximum output is 64K — both
smaller than the 1M/128K of the Opus and Sonnet tiers, which matters here
because `MAX_CONTEXT_TOKENS` has to stay well clear of the smaller number.

Google's rates are **not** hardcoded. I have no authoritative figure for them in
hand, and ADR 004's rule — do not fabricate a number you cannot verify — applies
to prices exactly as it applies to model IDs. They are configuration, they
default to zero, and a zero rate is reported by `/api/health` as unpriced rather
than silently costing nothing.

## Why an unpriced provider is dangerous, and what we do about it

A zero rate does not make a call free; it makes it *invisible to the breaker*.
So `estimate_cost` raises for an unpriced model rather than returning 0.0, and
the caller records the usage with a null cost and flags it. The failure is
loud and local instead of quiet and cumulative.

**This is the inner guard only.** Console spend limits at both providers are the
outer guard and are never removed on the grounds that this file exists —
application accounting has bugs; a console limit does not.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rate:
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float
    verified_on: str = ""
    """ISO date the figure was checked. Empty means unverified."""

    @property
    def is_priced(self) -> bool:
        return self.input_per_mtok > 0 or self.output_per_mtok > 0

    def cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok
        ) / 1_000_000


class UnpricedModelError(RuntimeError):
    """No rate is configured for this model.

    Deliberately an error. Returning 0.0 would let spend accumulate invisibly
    past a breaker that is watching a number which never moves.
    """


# Verified against the Anthropic pricing table on 2026-08-04.
RATES: dict[str, Rate] = {
    "claude-haiku-4-5": Rate(1.00, 5.00, verified_on="2026-08-04"),
    "claude-haiku-4-5-20251001": Rate(1.00, 5.00, verified_on="2026-08-04"),
}

# Google rates are supplied via configuration; see the module docstring.
GOOGLE_MODEL_PREFIXES = ("gemini-",)


def register(
    model: str, *, input_per_mtok: float, output_per_mtok: float, verified_on: str
) -> None:
    """Add or override a rate at startup, from configuration.

    `verified_on` is required and is not decorative — an operator who cannot say
    when they checked a price has not checked it.
    """
    if not verified_on:
        raise ValueError(f"refusing to register a rate for {model!r} with no verification date")
    RATES[model] = Rate(input_per_mtok, output_per_mtok, verified_on=verified_on)


_configured_from_environment = False


def configure_from_settings() -> None:
    """Load `MODEL_PRICES` into `RATES`. Idempotent.

    Called lazily from `rate_for` rather than from application startup, because
    the eval harness and the CLI scripts price their own calls and never run a
    FastAPI lifespan. A rate that exists only when the web server booted would
    silently zero out every number in `eval/report.md`.
    """
    global _configured_from_environment
    if _configured_from_environment:
        return
    # Imported here, not at module scope: `config` is the heavier module and
    # nothing else in pricing needs it.
    from api.config import get_settings

    settings = get_settings()
    _configured_from_environment = True
    for model, (input_per_mtok, output_per_mtok) in settings.model_prices.items():
        register(
            model,
            input_per_mtok=input_per_mtok,
            output_per_mtok=output_per_mtok,
            verified_on=settings.model_prices_verified_on,
        )


def rate_for(model: str) -> Rate | None:
    configure_from_settings()
    if model in RATES:
        return RATES[model]
    # Allow a versioned id to inherit its family's rate: `claude-haiku-4-5-20251001`
    # should resolve even if only `claude-haiku-4-5` was registered.
    for known, rate in RATES.items():
        if model.startswith(known):
            return rate
    return None


def estimate_cost(model: str, *, input_tokens: int, output_tokens: int) -> float:
    rate = rate_for(model)
    if rate is None or not rate.is_priced:
        raise UnpricedModelError(
            f"No verified price for {model!r}. Set it via configuration rather than "
            "guessing — an unpriced model spends money the circuit breaker cannot see."
        )
    return rate.cost(input_tokens=input_tokens, output_tokens=output_tokens)


def unpriced_models(models: Iterable[str]) -> list[str]:
    """Which of these models would spend money the breaker cannot see.

    It takes the models a deployment will *call*, not the ones it happens to
    have rates for. The earlier version asked the second question, and so
    answered "nothing is unpriced" on a configuration where every Gemini call
    was invisible — the set it iterated could not contain a model nobody had
    registered.
    """
    configure_from_settings()
    unpriced = set()
    for model in models:
        rate = rate_for(model)
        if rate is None or not rate.is_priced:
            unpriced.add(model)
    return sorted(unpriced)
