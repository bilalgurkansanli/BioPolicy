"""Cost accounting for the budget breaker.

Small file, high stakes: if these numbers are wrong the $30 ceiling is
decorative.
"""

from __future__ import annotations

import pytest

from api import pricing
from api.config import Settings
from api.pricing import UnpricedModelError, estimate_cost, rate_for, register, unpriced_models


def test_verified_haiku_rate() -> None:
    """$1.00 / $5.00 per million tokens, checked 2026-08-04."""
    rate = rate_for("claude-haiku-4-5")
    assert rate is not None
    assert (rate.input_per_mtok, rate.output_per_mtok) == (1.00, 5.00)
    assert rate.verified_on == "2026-08-04"


def test_a_versioned_id_inherits_its_family_rate() -> None:
    """`claude-haiku-4-5-20251001` must not fall through to unpriced."""
    assert rate_for("claude-haiku-4-5-20251001") is not None


def test_cost_arithmetic() -> None:
    # 10k input at $1/M + 2k output at $5/M = $0.01 + $0.01
    cost = estimate_cost("claude-haiku-4-5", input_tokens=10_000, output_tokens=2_000)
    assert cost == pytest.approx(0.02)


def test_a_realistic_answer_is_cheap_enough_for_the_budget() -> None:
    """Sanity-check the ceiling is reachable at all.

    A grounded answer is roughly 6k context in and 400 out, plus a verification
    pass. If one question cost dollars the whole design would be wrong.
    """
    answer = estimate_cost("claude-haiku-4-5", input_tokens=6_500, output_tokens=400)
    verify = estimate_cost("claude-haiku-4-5", input_tokens=6_000, output_tokens=300)

    per_question = answer + verify
    assert per_question < 0.02
    assert 30.0 / per_question > 1_000  # the budget buys >1000 questions


def test_an_unpriced_model_raises_rather_than_costing_zero() -> None:
    """The safety property.

    Returning 0.0 would let a provider spend real money behind a breaker
    watching a number that never moves — the failure would be invisible until
    the bill arrived.
    """
    with pytest.raises(UnpricedModelError, match="No verified price"):
        estimate_cost("some-unpriced-model", input_tokens=1_000, output_tokens=100)


def test_registering_a_rate_requires_a_verification_date() -> None:
    """An operator who cannot say when they checked a price has not checked it."""
    with pytest.raises(ValueError, match="verification date"):
        register("gemini-something", input_per_mtok=0.1, output_per_mtok=0.4, verified_on="")


def test_a_registered_rate_becomes_usable() -> None:
    register("test-model-xyz", input_per_mtok=2.0, output_per_mtok=8.0, verified_on="2026-08-04")
    assert estimate_cost("test-model-xyz", input_tokens=1_000_000, output_tokens=0) == 2.0


# --- which models are unpriced ------------------------------------------------
#
# This set is the whole safety property. It was previously computed over the
# rates that *exist*, which cannot contain a model nobody registered — so a
# deployment whose every Gemini call was invisible reported nothing wrong.


def test_unpriced_asks_about_the_models_that_will_be_called() -> None:
    assert unpriced_models(["claude-haiku-4-5", "gemini-nobody-priced-this"]) == [
        "gemini-nobody-priced-this"
    ]


def test_nothing_unpriced_when_every_called_model_has_a_rate() -> None:
    assert unpriced_models(["claude-haiku-4-5"]) == []


def test_priced_models_skips_capabilities_that_are_switched_off() -> None:
    """An empty model id means the capability is unavailable, not unpriced."""
    settings = Settings(
        app_env="development",
        gemini_fallback_model="",
        gemini_ocr_model="",
        _env_file=None,
    )
    assert "" not in settings.priced_models
    assert settings.anthropic_model in settings.priced_models


# --- rates arriving from configuration ---------------------------------------


def test_model_prices_parse_from_the_comma_form() -> None:
    settings = Settings(
        app_env="development",
        model_prices="gemini-embedding-001:0.15:0,gemini-3.6-flash:1.50:7.50",
        model_prices_verified_on="2026-08-09",
        _env_file=None,
    )
    assert settings.model_prices == {
        "gemini-embedding-001": (0.15, 0.0),
        "gemini-3.6-flash": (1.50, 7.50),
    }


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("gemini-3.6-flash:1.50", "model:input:output"),
        ("gemini-3.6-flash:1.50:7.50:extra", "model:input:output"),
        ("gemini-3.6-flash:cheap:7.50", "not a number"),
        (":1.50:7.50", "no model id"),
    ],
)
def test_a_malformed_price_names_the_entry(value: str, match: str) -> None:
    """A price parsed wrongly is worse than one absent: absent raises, wrong under-counts."""
    with pytest.raises(ValueError, match=match):
        Settings(app_env="development", model_prices=value, _env_file=None)


def test_prices_without_a_date_are_refused() -> None:
    with pytest.raises(ValueError, match="MODEL_PRICES_VERIFIED_ON"):
        Settings(
            app_env="development",
            model_prices="gemini-3.6-flash:1.50:7.50",
            model_prices_verified_on="",
            _env_file=None,
        )


def test_configured_prices_reach_the_rate_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """The path that was missing entirely: `register` existed, nothing called it."""
    settings = Settings(
        app_env="development",
        model_prices="gemini-test-only:2.00:4.00",
        model_prices_verified_on="2026-08-09",
        _env_file=None,
    )
    monkeypatch.setattr(pricing, "_configured_from_environment", False)
    monkeypatch.setattr("api.config.get_settings", lambda: settings)

    rate = rate_for("gemini-test-only")
    assert rate is not None
    assert (rate.input_per_mtok, rate.output_per_mtok) == (2.00, 4.00)
    assert rate.verified_on == "2026-08-09"
