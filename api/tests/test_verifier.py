"""Self-verification and the groundedness bands.

The single most important assertion in this file is
`test_the_verifier_is_never_shown_the_question`. Everything else the pass claims
to do depends on it: a verifier that can see the question starts judging whether
the answer *responds well*, and a fluent, on-topic, entirely invented answer
scores highly on that while failing the property we actually care about.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from api.generation import prompts
from api.generation.llm import (
    AllProvidersFailedError,
    FailoverLLM,
    MalformedResponseError,
    ProviderError,
    extract_json,
)
from api.generation.schemas import ClaimVerdict, VerificationResult
from api.generation.verifier import Verifier, classify
from api.retrieval.context import assemble
from api.tests.fakes import FailingLLM, ScriptedLLM
from api.tests.test_context import chunk

EXCERPT = "Sel ve su baskını teminatı 750.000 TL limit ve 3.500 TL muafiyet ile karşılanır."


def verdicts(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        {"claims": [{"claim": c, "support": s, "note": ""} for c, s in pairs]},
        ensure_ascii=False,
    )


# -----------------------------------------------------------------------------
# groundedness arithmetic
# -----------------------------------------------------------------------------


class TestGroundednessScore:
    def test_all_supported_scores_one(self) -> None:
        result = VerificationResult(
            claims=[
                ClaimVerdict(claim="a", support="SUPPORTED"),
                ClaimVerdict(claim="b", support="SUPPORTED"),
            ]
        )
        assert result.groundedness == 1.0

    def test_partial_counts_as_a_half(self) -> None:
        """A claim the verifier could only partly support is genuinely between.

        Collapsing PARTIAL to either extreme throws away the distinction the
        verifier was asked to make.
        """
        result = VerificationResult(
            claims=[
                ClaimVerdict(claim="a", support="SUPPORTED"),
                ClaimVerdict(claim="b", support="PARTIAL"),
            ]
        )
        assert result.groundedness == 0.75

    def test_all_unsupported_scores_zero(self) -> None:
        result = VerificationResult(claims=[ClaimVerdict(claim="a", support="UNSUPPORTED")])
        assert result.groundedness == 0.0

    def test_no_claims_scores_zero_not_one(self) -> None:
        """An empty verification verified nothing.

        Returning 1.0 would let an unverifiable answer sail through the top
        threshold — the exact opposite of what the pass is for.
        """
        assert VerificationResult(claims=[]).groundedness == 0.0


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (1.0, "serve"),
            (0.8, "serve"),
            (0.79, "warn"),
            (0.5, "warn"),
            (0.49, "suppress"),
            (0.0, "suppress"),
        ],
    )
    def test_thresholds(self, score: float, expected: str) -> None:
        assert classify(score) == expected

    def test_an_unknown_score_serves_rather_than_suppresses(self) -> None:
        """Verification not running is 'unknown', not 'bad'.

        Suppressing on None would turn a provider outage into a product that
        refuses everything — and it would look like caution rather than an
        incident, which is how it would survive unnoticed.
        """
        assert classify(None) == "serve"


# -----------------------------------------------------------------------------
# the pass itself
# -----------------------------------------------------------------------------


async def test_the_verifier_is_never_shown_the_question() -> None:
    """The design decision that makes this pass worth running."""
    llm = ScriptedLLM(verdicts(("Flood cover is 750.000 TL", "SUPPORTED")))
    context = assemble([chunk(EXCERPT)])

    await Verifier(llm).verify(draft="Sel teminatı 750.000 TL'dir.", context=context)

    sent = llm.payloads[0] + llm.systems[0]
    assert "Sel teminatı var mı" not in sent
    # The excerpts and the draft are present; nothing else is.
    assert EXCERPT in llm.payloads[0]
    assert "750.000" in llm.payloads[0]
    assert "question" not in llm.payloads[0].lower()


async def test_a_supported_draft_scores_high() -> None:
    llm = ScriptedLLM(
        verdicts(
            ("Flood cover is limited to 750.000 TL", "SUPPORTED"),
            ("A deductible of 3.500 TL applies", "SUPPORTED"),
        )
    )
    outcome = await Verifier(llm).verify(
        draft="Sel teminatı 750.000 TL, muafiyet 3.500 TL.", context=assemble([chunk(EXCERPT)])
    )

    assert outcome.result is not None
    assert outcome.groundedness == 1.0
    assert classify(outcome.groundedness) == "serve"


async def test_an_invented_claim_drags_the_score_below_the_serve_band() -> None:
    llm = ScriptedLLM(
        verdicts(
            ("Flood cover is limited to 750.000 TL", "SUPPORTED"),
            ("Business interruption is covered", "UNSUPPORTED"),
            ("Cover applies with no waiting period", "UNSUPPORTED"),
        )
    )
    outcome = await Verifier(llm).verify(draft="…", context=assemble([chunk(EXCERPT)]))

    assert outcome.result is not None
    assert outcome.groundedness == pytest.approx(1 / 3)
    assert classify(outcome.groundedness) == "suppress"


async def test_an_overstated_claim_lands_in_the_warn_band() -> None:
    """Directionally right, but drops a condition. Served with a visible flag."""
    llm = ScriptedLLM(
        verdicts(
            ("Flood damage is covered", "SUPPORTED"),
            ("Cover is unconditional", "PARTIAL"),
        )
    )
    outcome = await Verifier(llm).verify(draft="…", context=assemble([chunk(EXCERPT)]))

    assert outcome.result is not None
    assert classify(outcome.groundedness) == "warn"


async def test_the_verify_prompt_is_the_one_that_gets_sent() -> None:
    llm = ScriptedLLM(verdicts(("a", "SUPPORTED")))
    verifier = Verifier(llm)

    await verifier.verify(draft="…", context=assemble([chunk(EXCERPT)]))

    assert llm.systems[0] == prompts.load(prompts.VERIFY)
    assert verifier.prompt_version == "verify_v1"


# -----------------------------------------------------------------------------
# degrading honestly
# -----------------------------------------------------------------------------


async def test_a_provider_outage_returns_unknown_not_zero() -> None:
    """None means 'we do not know', and the caller must not read it as 'bad'."""
    outcome = await Verifier(FailingLLM()).verify(draft="…", context=assemble([chunk(EXCERPT)]))

    assert outcome.result is None
    assert classify(None) == "serve"


async def test_an_unreadable_response_returns_unknown() -> None:
    outcome = await Verifier(ScriptedLLM("I'm not going to answer in JSON, sorry.")).verify(
        draft="…", context=assemble([chunk(EXCERPT)])
    )

    assert outcome.result is None


async def test_verification_is_skipped_when_there_is_nothing_to_verify() -> None:
    llm = ScriptedLLM()  # would raise if called

    assert (await Verifier(llm).verify(draft="", context=assemble([chunk(EXCERPT)]))).result is None
    assert (await Verifier(llm).verify(draft="something", context=assemble([]))).result is None
    assert llm.call_count == 0


# -----------------------------------------------------------------------------
# failover
# -----------------------------------------------------------------------------


async def test_failover_moves_to_the_next_provider_on_an_outage() -> None:
    primary = FailingLLM(name="anthropic")
    fallback = ScriptedLLM(verdicts(("a", "SUPPORTED")))
    chain = FailoverLLM(providers=[primary, fallback])

    outcome = await Verifier(chain).verify(draft="…", context=assemble([chunk(EXCERPT)]))

    assert outcome.result is not None
    assert primary.call_count == 1
    assert fallback.call_count == 1
    assert chain.attempted == ["anthropic", "scripted"]


async def test_failover_does_not_retry_a_provider_that_answered_badly() -> None:
    """A bad response is not an outage.

    The same model will produce the same class of output again; asking twice
    just spends the money twice.
    """
    primary = ScriptedLLM("not json at all")
    fallback = ScriptedLLM(verdicts(("a", "SUPPORTED")))

    outcome = await Verifier(FailoverLLM(providers=[primary, fallback])).verify(
        draft="…", context=assemble([chunk(EXCERPT)])
    )

    assert outcome.result is None  # unreadable, and not retried
    assert fallback.call_count == 0


async def test_every_provider_failing_raises() -> None:
    chain = FailoverLLM(providers=[FailingLLM("a"), FailingLLM("b")])

    with pytest.raises(AllProvidersFailedError, match=r"a:.*b:"):
        await chain.complete(system="s", turns=[], max_tokens=10)


def test_a_chain_needs_at_least_one_provider() -> None:
    with pytest.raises(ValueError, match="at least one"):
        FailoverLLM(providers=[])


async def test_streaming_fails_over_before_the_first_token() -> None:
    chain = FailoverLLM(providers=[FailingLLM("anthropic"), ScriptedLLM("cover is granted")])

    tokens = [t async for t in chain.stream(system="s", turns=[], max_tokens=50)]

    assert "".join(tokens).strip() == "cover is granted"
    assert chain.attempted == ["anthropic", "scripted"]


async def test_a_mid_stream_failure_is_not_papered_over() -> None:
    """Once text has reached the user, switching providers would append a
    second, differently-worded answer onto the first — producing a reply no
    single model actually wrote. Failing honestly is the correct outcome."""

    class DiesMidStream:
        name = "flaky"
        model = "flaky-model"

        async def complete(self, **kwargs: object) -> object:  # pragma: no cover
            raise NotImplementedError

        async def stream(self, **kwargs: object) -> AsyncIterator[str]:
            yield "Sel teminatı "
            raise ProviderError("connection reset")

    chain = FailoverLLM(providers=[DiesMidStream(), ScriptedLLM("a completely different answer")])  # type: ignore[list-item]

    emitted: list[str] = []
    with pytest.raises(ProviderError, match="connection reset"):
        async for token in chain.stream(system="s", turns=[], max_tokens=50):
            emitted.append(token)

    assert emitted == ["Sel teminatı "]
    assert "different answer" not in "".join(emitted)


# -----------------------------------------------------------------------------
# tolerant JSON extraction
# -----------------------------------------------------------------------------


class TestExtractJson:
    """Models mostly comply with 'JSON only' and sometimes do not.

    Being strict would turn a cosmetic deviation into a failed answer, so the
    parser is tolerant about the wrapper and strict about the content.
    """

    def test_a_clean_object(self) -> None:
        assert extract_json('{"answer_found": true}') == {"answer_found": True}

    def test_inside_a_markdown_fence(self) -> None:
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_inside_an_unlabelled_fence(self) -> None:
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_surrounded_by_prose(self) -> None:
        text = 'Here is the result:\n{"a": 1}\nLet me know if you need more.'
        assert extract_json(text) == {"a": 1}

    def test_turkish_content_survives(self) -> None:
        parsed = extract_json('{"answer": "Sel teminatı 750.000 TL\'dir."}')
        assert parsed["answer"] == "Sel teminatı 750.000 TL'dir."

    @pytest.mark.parametrize("text", ["", "no json here", "[1, 2, 3]", "{not valid}"])
    def test_unparseable_input_raises(self, text: str) -> None:
        with pytest.raises(MalformedResponseError):
            extract_json(text)
