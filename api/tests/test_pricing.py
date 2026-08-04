"""Cost accounting for the budget breaker.

Small file, high stakes: if these numbers are wrong the $30 ceiling is
decorative.
"""

from __future__ import annotations

import pytest

from api.pricing import UnpricedModelError, estimate_cost, rate_for, register


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
