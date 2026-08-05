"""The entailment check, and what it is for.

These tests are written against the failure the evaluation found rather than
against the code: an answer whose every claim is supported and which still does
not follow, because the excerpts are about something adjacent. That failure has
a name in `eval/report.md` and a worked example — a theft clause answering a
question about a car — and the example is the first test here.
"""

from __future__ import annotations

import json

import pytest

from api.generation.answerer import Answerer
from api.generation.entailment import EntailmentChecker
from api.generation.schemas import EntailmentResult
from api.retrieval.context import AssembledContext, assemble
from api.tests.fakes import FailingLLM, ScriptedLLM
from api.tests.test_context import chunk

THEFT = (
    "Madde 6 — Hırsızlık. Sigortalı adresteki eşyaların çalınması sonucu oluşan "
    "zararlar 250.000 TL limitle karşılanır."
)


def context_of(*contents: str) -> AssembledContext:
    return assemble([chunk(c, page=i + 1) for i, c in enumerate(contents)])


def verdict(value: str, reason: str = "") -> str:
    return json.dumps({"verdict": value, "reason": reason})


# -----------------------------------------------------------------------------
# the check itself
# -----------------------------------------------------------------------------


async def test_the_question_is_sent_to_the_checker() -> None:
    """The whole point, and the one thing that distinguishes it from the verifier.

    `api/generation/verifier.py` is deliberately question-blind. This pass is
    the complement, and if the question ever stopped reaching it the check would
    silently degrade into a worse copy of the verifier.
    """
    llm = ScriptedLLM(verdict("ENTAILED"))

    await EntailmentChecker(llm).check(
        question="Çalınan arabam karşılanıyor mu?",
        draft="Evet, hırsızlık karşılanıyor.",
        context=context_of(THEFT),
    )

    assert "Çalınan arabam" in llm.payloads[0]
    assert THEFT[:30] in llm.payloads[0]


async def test_a_verdict_is_parsed() -> None:
    outcome = await EntailmentChecker(
        ScriptedLLM(verdict("RELATED_ONLY", "contents, not vehicles"))
    ).check(
        question="Çalınan arabam karşılanıyor mu?",
        draft="Evet, araba dahil.",
        context=context_of(THEFT),
    )

    assert outcome.result is not None
    assert outcome.result.verdict == "RELATED_ONLY"
    assert outcome.usage  # the call was billed and is recorded


async def test_an_outage_is_unknown_rather_than_bad() -> None:
    """A provider failure must not become a wave of withheld answers."""
    outcome = await EntailmentChecker(FailingLLM()).check(
        question="…", draft="…", context=context_of(THEFT)
    )

    assert outcome.result is None


async def test_an_unreadable_verdict_is_unknown_but_still_billed() -> None:
    outcome = await EntailmentChecker(ScriptedLLM("not json at all")).check(
        question="…", draft="…", context=context_of(THEFT)
    )

    assert outcome.result is None
    assert outcome.usage


async def test_nothing_is_asked_about_an_empty_context() -> None:
    """No excerpts, nothing to entail, and no reason to pay for the question."""
    llm = ScriptedLLM(verdict("ENTAILED"))
    outcome = await EntailmentChecker(llm).check(
        question="…", draft="Bir cevap.", context=assemble([])
    )

    assert outcome.result is None
    assert llm.call_count == 0


# -----------------------------------------------------------------------------
# which verdicts license an answer
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "licensed"),
    [
        ("ENTAILED", True),
        # Deliberately permissive: the checker admitting it cannot tell must not
        # become a censor. A weak checker would otherwise withhold everything.
        ("UNSURE", True),
        ("RELATED_ONLY", False),
        ("CONTRADICTED", False),
    ],
)
def test_only_a_positive_finding_withholds(value: str, licensed: bool) -> None:
    assert EntailmentResult(verdict=value).licenses_the_answer is licensed


# -----------------------------------------------------------------------------
# in the pipeline
# -----------------------------------------------------------------------------


ANSWER = json.dumps(
    {
        "answer_found": True,
        "answer": "Evet, hırsızlık karşılandığı için arabanız da dahildir.",
        "citations": [{"chunk_id": "C1", "quote": "eşyaların çalınması sonucu oluşan"}],
        "confidence": "high",
        "caveats": [],
    },
    ensure_ascii=False,
)


async def test_the_worked_example_from_the_report_is_withheld() -> None:
    """Asked about a car, answered from a contents clause.

    Every earlier mechanism passes this: the quote is verbatim, and the claim
    "theft is covered" is supported by an excerpt that says exactly that. The
    step from *contents* to *a car* is the one nothing else examines.
    """
    answerer = Answerer(
        ScriptedLLM(ANSWER),
        entailment=EntailmentChecker(
            ScriptedLLM(verdict("RELATED_ONLY", "clause covers contents, not vehicles"))
        ),
        enable_verification=False,
    )

    outcome = await answerer.answer(
        question="Çalınan arabam karşılanıyor mu?", context=context_of(THEFT)
    )

    assert outcome.answer.refused is True
    assert outcome.answer.suppressed is True
    assert outcome.answer.suppression_reason == "not_entailed"
    # The drafted text never reaches the caller.
    assert "arabanız da dahildir" not in outcome.answer.answer


async def test_an_entailed_answer_is_served_and_says_so() -> None:
    answerer = Answerer(
        ScriptedLLM(ANSWER),
        entailment=EntailmentChecker(ScriptedLLM(verdict("ENTAILED"))),
        enable_verification=False,
    )

    outcome = await answerer.answer(question="Hırsızlık kapsanıyor mu?", context=context_of(THEFT))

    assert outcome.answer.refused is False
    assert outcome.answer.entailment == "ENTAILED"


async def test_the_check_can_be_switched_off_for_the_ablation() -> None:
    """It is configuration for measurement, like the three mechanisms before it."""
    checker = ScriptedLLM(verdict("RELATED_ONLY"))
    answerer = Answerer(
        ScriptedLLM(ANSWER),
        entailment=EntailmentChecker(checker),
        enable_verification=False,
        enable_entailment_check=False,
    )

    outcome = await answerer.answer(question="…", context=context_of(THEFT))

    assert checker.call_count == 0
    assert outcome.answer.refused is False
    assert outcome.answer.entailment is None


async def test_its_tokens_are_recorded() -> None:
    """A mechanism that costs money and is not counted is a mechanism whose
    cost cannot be compared against what it catches."""
    answerer = Answerer(
        ScriptedLLM(ANSWER),
        entailment=EntailmentChecker(ScriptedLLM(verdict("ENTAILED"))),
        enable_verification=False,
    )

    outcome = await answerer.answer(question="…", context=context_of(THEFT))

    assert [u.operation for u in outcome.usage] == ["answer", "entail"]
