"""Grounded answering — where the three mechanisms of Section 7 compose.

The order is not arbitrary, and each step can only end the pipeline in the
direction of *less* confidence:

1. **No context → refuse without calling anything.** If retrieval found nothing,
   there is no possible grounded answer, and asking the model anyway would spend
   money to obtain a guess.
2. **Generate** under the strict prompt, as structured JSON.
3. **Bind citations.** Quotes that do not appear in the chunks they name are
   dropped. If every citation on a positive answer is dropped, the answer is
   suppressed — a caught hallucination.
4. **Verify.** Claims are scored against the excerpts, and a low score suppresses
   the answer even when its citations were individually valid. Citations can all
   be real while the sentence built around them is not.
5. **Check entailment.** Do the excerpts *settle* the question, or only touch it?
   Every claim can be supported and the answer still not follow, because the
   excerpts are about something adjacent — a theft clause answering a question
   about a car. This is the one pass that is shown the question, which is
   exactly why it can see a failure the question-blind verifier cannot
   (`api/generation/entailment.py`).

Nothing downstream can upgrade an answer. A refusal never becomes an answer, and
a suppressed answer is never revived.

## Each mechanism is switchable

`enable_citation_binding` and `enable_verification` exist so the evaluation
harness can run the same golden dataset with the layers off, then on, and
publish the difference. They are configuration for measurement, not feature
flags to be left half-on in production.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from api.generation import prompts
from api.generation.citations import bind
from api.generation.entailment import EntailmentChecker
from api.generation.llm import (
    LLMProvider,
    MalformedResponseError,
    ProviderError,
    Turn,
    UsageRecord,
    extract_json,
)
from api.generation.schemas import (
    AnswerPayload,
    BoundCitation,
    DroppedCitation,
    GroundedAnswer,
)
from api.generation.verifier import Verifier, classify
from api.logging_config import get_logger
from api.retrieval.context import AssembledContext

log = get_logger(__name__)

# A ceiling, not a budget: almost every answer stops well short of it and is
# billed for what it wrote. That asymmetry is why this is not set tight.
#
# It was 1200, and a truncated reply is the one outcome that costs the full
# ceiling and returns nothing at all — the JSON does not parse, the answer is
# discarded, and the user is shown "try again later" for a question the document
# answers. Being 20% too small cost 100% of those calls.
#
# Measured on the AXA policy, same question, same retrieved context: 1,481 /
# 1,582 / 2,068 tokens. That spread is the reason for the headroom rather than
# the mean — temperature is 0 but the length of a list-shaped answer is not
# stable across calls, so a ceiling set just above the average truncates a third
# of the time. 3000 is ~45% above the longest observed.
#
# An answer approaching this is half as long as the entire 6,000-token context
# it may draw on, which is a prompt problem rather than a ceiling problem.
ANSWER_MAX_TOKENS = 3000

# Shown when an answer is withheld, or when there is nothing to answer from.
#
# WHY fixed strings rather than asking the model to write the refusal: a
# suppressed answer means the model has already demonstrated it will assert
# things the document does not support. Asking that same model to explain itself
# invites a fluent apology containing yet another unsupported claim. And when
# the reason is a provider outage there is no model available to ask.
REFUSALS: dict[str, dict[str, str]] = {
    "tr": {
        "no_context": (
            "Bu soruyla ilgili bir bölüm belgede bulunamadı. Soruyu belgede geçen "
            "terimlerle yeniden ifade etmeyi deneyebilirsiniz."
        ),
        "off_topic": (
            "Bu soru, bu belgenin konusuyla ilgili görünmüyor. Belge yalnızca kendi "
            "içeriği hakkındaki sorulara yanıt verebilir."
        ),
        "no_valid_citations": (
            "Bu soruya bir yanıt taslağı oluşturuldu, ancak dayandığı alıntılar belgede "
            "doğrulanamadı. Doğrulanamayan bir yanıtı göstermemeyi tercih ediyoruz."
        ),
        "low_groundedness": (
            "Oluşturulan yanıtın belgedeki metinle yeterince desteklendiği doğrulanamadı, "
            "bu nedenle gösterilmiyor."
        ),
        "not_entailed": (
            "Belgede bu konuya yakın maddeler var, ama sorduğunuz şeyi doğrudan "
            "karara bağlamıyorlar. Yakın bir maddeden çıkarım yapmaktansa "
            "cevaplamamayı tercih ediyoruz."
        ),
        "unavailable": ("Yanıt şu anda oluşturulamıyor. Lütfen biraz sonra tekrar deneyin."),
    },
    "en": {
        "no_context": (
            "No passage in this document appears to address that question. You could try "
            "rephrasing it using wording that appears in the document."
        ),
        "off_topic": (
            "That question does not appear to be about this document. It can only answer "
            "questions about its own contents."
        ),
        "no_valid_citations": (
            "An answer was drafted, but the passages it relied on could not be verified "
            "against the document. We would rather show you nothing than something "
            "unverified."
        ),
        "low_groundedness": (
            "The drafted answer could not be confirmed as sufficiently supported by the "
            "document, so it is not being shown."
        ),
        "not_entailed": (
            "The document has passages near this subject, but they do not settle the "
            "question you asked. We would rather not answer than reason from an "
            "adjacent clause."
        ),
        "unavailable": "An answer cannot be produced right now. Please try again shortly.",
    },
}


def refusal_text(language: str, key: str) -> str:
    return REFUSALS.get(language, REFUSALS["en"]).get(key, REFUSALS["en"][key])


@dataclass(slots=True)
class AnswerOutcome:
    """The answer plus everything the caller must record about producing it."""

    answer: GroundedAnswer
    usage: list[UsageRecord] = field(default_factory=list)
    prompt_version: str = prompts.ANSWER
    model: str = ""

    @property
    def cost_relevant_tokens(self) -> int:
        return sum(u.input_tokens + u.output_tokens for u in self.usage)


class Answerer:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        verifier: Verifier | None = None,
        entailment: EntailmentChecker | None = None,
        enable_citation_binding: bool = True,
        enable_verification: bool = True,
        enable_entailment_check: bool = True,
        max_tokens: int = ANSWER_MAX_TOKENS,
        prompt_name: str = prompts.ANSWER,
    ) -> None:
        self._llm = llm
        self._verifier = verifier
        self._entailment = entailment
        self._bind = enable_citation_binding
        self._verify = enable_verification and verifier is not None
        self._entail = enable_entailment_check and entailment is not None
        self._max_tokens = max_tokens
        # Swappable so the evaluation can run the same pipeline against the
        # strict grounding prompt and a naive one. The prompt is the largest
        # single lever in this system and it belongs in the ablation alongside
        # the mechanisms, not held fixed underneath them.
        self._prompt_name = prompt_name

    async def answer(
        self,
        *,
        question: str,
        context: AssembledContext,
        language: str = "tr",
        on_stage: Callable[[str], Awaitable[None]] | None = None,
    ) -> AnswerOutcome:
        """Produce a grounded answer, or a refusal.

        `on_stage` is awaited when the pipeline moves to a step the caller may
        want to show. Only the generation → verification boundary is reported,
        because it is the only one long enough for a user to notice and the only
        one whose label would otherwise be a guess: this method knows whether
        verification is going to run at all, and the HTTP layer does not.
        """
        usage: list[UsageRecord] = []

        # 1. Nothing retrieved. Refuse without spending anything.
        if context.is_empty:
            log.info("refused_no_context")
            return AnswerOutcome(
                answer=_refusal(language, "no_context", reason=None), model=self._llm.model
            )

        # 2. Generate.
        try:
            response = await self._llm.complete(
                system=prompts.render(self._prompt_name, reply_language=_language_name(language)),
                turns=[Turn(role="user", content=_user_turn(question, context))],
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
        except ProviderError as exc:
            log.error("answer_unavailable", error=str(exc))
            return AnswerOutcome(
                answer=_refusal(language, "unavailable", reason=None), model=self._llm.model
            )

        usage.append(UsageRecord.from_response("answer", response))

        try:
            payload = AnswerPayload.model_validate(extract_json(response.text))
        except (MalformedResponseError, ValueError) as exc:
            log.error("answer_unreadable", error=str(exc))
            return AnswerOutcome(
                answer=_refusal(language, "unavailable", reason=None),
                usage=usage,
                model=response.model,
            )

        # 3. An honest refusal from the model. This is a correct outcome and is
        #    passed through unchanged — it is not suppression.
        if not payload.answer_found:
            log.info("model_refused", confidence=payload.confidence)
            return AnswerOutcome(
                answer=GroundedAnswer(
                    answer=payload.answer or refusal_text(language, "no_context"),
                    refused=True,
                    confidence=payload.confidence,
                    caveats=payload.caveats,
                ),
                usage=usage,
                model=response.model,
            )

        # 4. Citation binding.
        kept: list[BoundCitation] = []
        dropped: list[DroppedCitation] = []
        if self._bind:
            outcome = bind(payload, context)
            kept, dropped = outcome.kept, outcome.dropped
            if outcome.suppressed:
                return AnswerOutcome(
                    answer=_refusal(language, "no_valid_citations", reason="no_valid_citations"),
                    usage=usage,
                    model=response.model,
                )
        else:
            # Binding disabled for an ablation run. Citations pass through
            # unchecked, which is the point of the comparison.
            outcome = bind(payload, context)
            kept = outcome.kept

        # 5. Verification.
        groundedness: float | None = None
        verified = False
        if self._verify and self._verifier is not None:
            if on_stage is not None:
                await on_stage("verifying")
            verification = await self._verifier.verify(draft=payload.answer, context=context)
            # Recorded before the suppression check below: a verification that
            # decided to withhold the answer still cost money, and the budget
            # breaker has to see it.
            usage.extend(verification.usage)
            if verification.result is not None:
                groundedness = verification.result.groundedness
                verified = True

            if classify(groundedness) == "suppress":
                return AnswerOutcome(
                    answer=_refusal(language, "low_groundedness", reason="low_groundedness"),
                    usage=usage,
                    model=response.model,
                )

        # 6. Entailment. Last, because it is the most expensive question to ask
        #    and there is no point asking it about an answer already withheld.
        #    It can only withhold — never revive — like every step above it.
        entailment = None
        if self._entail and self._entailment is not None:
            if on_stage is not None:
                await on_stage("verifying")
            checked = await self._entailment.check(
                question=question, draft=payload.answer, context=context
            )
            usage.extend(checked.usage)
            entailment = checked.result

            if entailment is not None and not entailment.licenses_the_answer:
                log.info(
                    "suppressed_not_entailed",
                    verdict=entailment.verdict,
                    reason=entailment.reason,
                )
                return AnswerOutcome(
                    answer=_refusal(language, "not_entailed", reason="not_entailed"),
                    usage=usage,
                    model=response.model,
                )

        return AnswerOutcome(
            answer=GroundedAnswer(
                answer=payload.answer,
                refused=False,
                citations=kept,
                dropped_citations=dropped,
                confidence=payload.confidence,
                caveats=payload.caveats,
                groundedness=groundedness,
                verified=verified,
                entailment=entailment.verdict if entailment else None,
            ),
            usage=usage,
            model=response.model,
        )


def off_topic_refusal(language: str) -> AnswerOutcome:
    """Refuse a question the retrieval floor judged to be about something else.

    Produced without calling any model, which is the entire point: the outcome
    carries no usage, so the caller records nothing and the breaker sees nothing,
    because nothing was spent.

    Lives here rather than in the router so that every refusal this system can
    emit is written in one file, in both languages, next to the reasoning for
    why refusals are fixed strings (see REFUSALS above).

    `refused`, not `suppressed`. Suppression means an answer existed and was
    withheld; here no answer was ever drafted, and the eval's safety metrics
    depend on not confusing the two.
    """
    return AnswerOutcome(answer=_refusal(language, "off_topic", reason=None))


def _refusal(language: str, key: str, *, reason: str | None) -> GroundedAnswer:
    return GroundedAnswer(
        answer=refusal_text(language, key),
        refused=True,
        confidence="low",
        suppressed=reason is not None,
        suppression_reason=reason,
    )


def _user_turn(question: str, context: AssembledContext) -> str:
    return f"# Excerpts from the document\n\n{context.text}\n\n# Question\n\n{question}"


def _language_name(code: str) -> str:
    return {"tr": "Turkish", "en": "English"}.get(code, "English")
