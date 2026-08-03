"""End-to-end grounded answering.

These assert the composition rule: each stage can only move an answer toward
*less* confidence. A refusal never becomes an answer, a suppressed answer is
never revived, and no stage downstream of generation can add certainty.
"""

from __future__ import annotations

import json

from api.generation.answerer import Answerer, refusal_text
from api.generation.verifier import Verifier
from api.retrieval.context import AssembledContext, assemble
from api.tests.fakes import FailingLLM, ScriptedLLM
from api.tests.test_context import chunk

FLOOD = (
    "Sel ve su baskını teminatı; suyun risk adresine girmesi sonucu oluşan zararları "
    "750.000 TL limit ve 3.500 TL muafiyet ile karşılar."
)


def drafted(
    *,
    found: bool = True,
    answer: str = "Sel teminatı 750.000 TL limitle karşılanır.",
    citations: list[dict[str, str]] | None = None,
) -> str:
    return json.dumps(
        {
            "answer_found": found,
            "answer": answer,
            "citations": citations if citations is not None else [],
            "confidence": "high",
            "caveats": [],
        },
        ensure_ascii=False,
    )


def verdicts(*supports: str) -> str:
    return json.dumps(
        {"claims": [{"claim": f"claim {i}", "support": s} for i, s in enumerate(supports)]}
    )


GOOD_CITE = [{"chunk_id": "C1", "quote": "750.000 TL limit ve 3.500 TL muafiyet"}]
FAKE_CITE = [{"chunk_id": "C1", "quote": "sel teminatı sınırsız olarak karşılanır"}]


def context() -> AssembledContext:
    return assemble([chunk(FLOOD)])


# -----------------------------------------------------------------------------
# the happy path
# -----------------------------------------------------------------------------


async def test_a_supported_answer_is_served_with_its_citation() -> None:
    llm = ScriptedLLM(drafted(citations=GOOD_CITE))
    verifier = Verifier(ScriptedLLM(verdicts("SUPPORTED", "SUPPORTED")))

    outcome = await Answerer(llm, verifier=verifier).answer(
        question="Sel hasarı kapsanıyor mu?", context=context()
    )

    assert outcome.answer.refused is False
    assert outcome.answer.suppressed is False
    assert len(outcome.answer.citations) == 1
    assert outcome.answer.citations[0].page == 1
    assert outcome.answer.groundedness == 1.0
    assert outcome.answer.verified is True


async def test_usage_is_recorded_for_every_billable_call() -> None:
    """The budget breaker is only real if this is."""
    outcome = await Answerer(
        ScriptedLLM(drafted(citations=GOOD_CITE)),
        verifier=Verifier(ScriptedLLM(verdicts("SUPPORTED"))),
    ).answer(question="…", context=context())

    assert [u.operation for u in outcome.usage] == ["answer"]
    assert outcome.cost_relevant_tokens > 0


# -----------------------------------------------------------------------------
# refusing correctly
# -----------------------------------------------------------------------------


async def test_empty_retrieval_refuses_without_calling_the_model() -> None:
    """No possible grounded answer exists, so spending money to guess is wrong."""
    llm = ScriptedLLM()  # would raise if called

    outcome = await Answerer(llm).answer(
        question="Siber saldırı kapsanıyor mu?", context=assemble([])
    )

    assert llm.call_count == 0
    assert outcome.answer.refused is True
    assert outcome.answer.suppressed is False  # nothing was withheld; nothing existed


async def test_a_model_refusal_passes_through_unchanged() -> None:
    """`answer_found: false` is a correct outcome, not a failure to suppress."""
    outcome = await Answerer(
        ScriptedLLM(drafted(found=False, answer="Bu belge iş kesintisinden söz etmiyor."))
    ).answer(question="İş kesintisi kapsanıyor mu?", context=context())

    assert outcome.answer.refused is True
    assert outcome.answer.suppressed is False
    assert "iş kesintisi" in outcome.answer.answer.lower()


async def test_refusals_are_written_in_the_users_language() -> None:
    tr = await Answerer(ScriptedLLM()).answer(question="…", context=assemble([]), language="tr")
    en = await Answerer(ScriptedLLM()).answer(question="…", context=assemble([]), language="en")

    assert tr.answer.answer == refusal_text("tr", "no_context")
    assert en.answer.answer == refusal_text("en", "no_context")
    assert tr.answer.answer != en.answer.answer


async def test_an_unknown_language_falls_back_to_english() -> None:
    outcome = await Answerer(ScriptedLLM()).answer(
        question="…", context=assemble([]), language="de"
    )
    assert outcome.answer.answer == refusal_text("en", "no_context")


# -----------------------------------------------------------------------------
# suppression
# -----------------------------------------------------------------------------


async def test_an_answer_with_only_fabricated_citations_is_suppressed() -> None:
    """A caught hallucination: the answer existed and was withheld."""
    outcome = await Answerer(ScriptedLLM(drafted(citations=FAKE_CITE))).answer(
        question="Sel hasarı kapsanıyor mu?", context=context()
    )

    assert outcome.answer.refused is True
    assert outcome.answer.suppressed is True
    assert outcome.answer.suppression_reason == "no_valid_citations"
    # The invented text never reaches the user.
    assert "750.000" not in outcome.answer.answer


async def test_a_low_groundedness_answer_is_suppressed_despite_valid_citations() -> None:
    """Citations can all be real while the sentence built around them is not.

    This is why verification runs after binding rather than instead of it.
    """
    llm = ScriptedLLM(drafted(citations=GOOD_CITE))
    verifier = Verifier(ScriptedLLM(verdicts("UNSUPPORTED", "UNSUPPORTED", "SUPPORTED")))

    outcome = await Answerer(llm, verifier=verifier).answer(question="…", context=context())

    assert outcome.answer.suppressed is True
    assert outcome.answer.suppression_reason == "low_groundedness"


async def test_a_middling_score_is_served_with_the_score_exposed() -> None:
    llm = ScriptedLLM(drafted(citations=GOOD_CITE))
    verifier = Verifier(ScriptedLLM(verdicts("SUPPORTED", "PARTIAL", "UNSUPPORTED", "SUPPORTED")))

    outcome = await Answerer(llm, verifier=verifier).answer(question="…", context=context())

    assert outcome.answer.refused is False
    assert outcome.answer.groundedness == 0.625  # warn band
    assert outcome.answer.verified is True


# -----------------------------------------------------------------------------
# degrading honestly
# -----------------------------------------------------------------------------


async def test_a_provider_outage_produces_a_refusal_not_a_crash() -> None:
    outcome = await Answerer(FailingLLM()).answer(question="…", context=context())

    assert outcome.answer.refused is True
    assert outcome.answer.answer == refusal_text("tr", "unavailable")


async def test_an_unreadable_model_response_produces_a_refusal() -> None:
    outcome = await Answerer(ScriptedLLM("I'd be happy to help with that!")).answer(
        question="…", context=context()
    )

    assert outcome.answer.refused is True
    assert outcome.usage  # the call still cost money and is still recorded


async def test_a_verifier_outage_does_not_suppress_a_good_answer() -> None:
    """An outage must not silently turn into a product that refuses everything."""
    outcome = await Answerer(
        ScriptedLLM(drafted(citations=GOOD_CITE)), verifier=Verifier(FailingLLM())
    ).answer(question="…", context=context())

    assert outcome.answer.refused is False
    assert outcome.answer.groundedness is None
    assert outcome.answer.verified is False  # honestly reported as unverified


# -----------------------------------------------------------------------------
# ablation switches
# -----------------------------------------------------------------------------


async def test_disabling_binding_lets_a_fabricated_citation_through() -> None:
    """The 'before' column of the evaluation table.

    This is what the product looks like without its central mechanism, and the
    test exists so that number is produced by a real code path rather than an
    argument.
    """
    outcome = await Answerer(
        ScriptedLLM(drafted(citations=FAKE_CITE)), enable_citation_binding=False
    ).answer(question="…", context=context())

    assert outcome.answer.refused is False
    assert outcome.answer.suppressed is False


async def test_disabling_verification_skips_the_second_call() -> None:
    verifier_llm = ScriptedLLM(verdicts("UNSUPPORTED"))

    outcome = await Answerer(
        ScriptedLLM(drafted(citations=GOOD_CITE)),
        verifier=Verifier(verifier_llm),
        enable_verification=False,
    ).answer(question="…", context=context())

    assert verifier_llm.call_count == 0
    assert outcome.answer.groundedness is None
    assert outcome.answer.refused is False


async def test_verification_is_skipped_when_no_verifier_is_configured() -> None:
    outcome = await Answerer(ScriptedLLM(drafted(citations=GOOD_CITE))).answer(
        question="…", context=context()
    )

    assert outcome.answer.verified is False
    assert outcome.answer.refused is False


# -----------------------------------------------------------------------------
# prompt wiring
# -----------------------------------------------------------------------------


async def test_the_question_and_excerpts_both_reach_the_answering_model() -> None:
    llm = ScriptedLLM(drafted(citations=GOOD_CITE))

    await Answerer(llm).answer(question="Sel hasarı kapsanıyor mu?", context=context())

    assert "Sel hasarı kapsanıyor mu?" in llm.payloads[0]
    assert "750.000 TL" in llm.payloads[0]
    assert "[C1]" in llm.payloads[0]


async def test_the_reply_language_is_injected_into_the_system_prompt() -> None:
    llm = ScriptedLLM(drafted(citations=GOOD_CITE))

    await Answerer(llm).answer(question="…", context=context(), language="tr")

    assert "Answer in Turkish" in llm.systems[0]
    assert "$reply_language" not in llm.systems[0]  # substitution actually happened
