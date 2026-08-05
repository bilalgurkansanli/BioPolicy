"""The entailment check — the mechanism the evaluation asked for.

## Why this exists

The 2×2 ablation in `eval/report.md` found that citation binding and
self-verification changed **no decisions** while adding roughly 55% to the cost
of every question. The report also named the reason, and it is worth repeating
exactly because it is the whole justification for this file:

> The naive prompt's errors are *correct citations supporting an unwarranted
> inference*: asked whether a stolen car is covered, it quotes the theft clause
> accurately and then concludes the car is included. Binding checks that the
> quote is real — it is. Verification checks the claim against the excerpt — the
> excerpt does say theft is covered. Neither mechanism is built to catch a valid
> quote used to support a conclusion the document never draws.

So this is not a fourth opinion on the same question. It asks a different one.

## The division of labour, and why the verifier cannot do this

`api/generation/verifier.py` is **deliberately not shown the question**. That is
the decision which makes it worth running: a verifier that knows the question
drifts toward judging whether the answer *responds well*, which a fluent
invention does easily.

The same decision is exactly why it cannot see this failure. "Is the car
covered?" answered with "theft is covered" decomposes into the claim *theft is
covered*, which the excerpt supports. The unwarranted step lives in the relation
between the question and the answer, and that relation is the one thing the
verifier is blind to by design.

This check is the complement: it **is** shown the question, and it judges only
whether the excerpts settle it. Two passes, two blind spots, arranged so that
neither one's blind spot is shared.

## What it can cost

An answer that is correct but whose evidence the checker judges insufficient is
withheld — a false refusal. That is a real cost and it is measurable, which is
the point: the evaluation reports refusal accuracy and false-refusal rate side
by side, and this mechanism can only be justified by moving the first further
than it moves the second.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.generation import prompts
from api.generation.llm import (
    LLMProvider,
    MalformedResponseError,
    ProviderError,
    Turn,
    UsageRecord,
    extract_json,
)
from api.generation.schemas import EntailmentResult
from api.logging_config import get_logger
from api.retrieval.context import AssembledContext

log = get_logger(__name__)

# One verdict and one short sentence. Anything longer is the model explaining
# itself, which costs money and changes nothing.
ENTAILMENT_MAX_TOKENS = 300


@dataclass(slots=True)
class EntailmentOutcome:
    """The verdict, or `None` when the check could not be run.

    `None` means *unknown*, not *bad* — the same convention the verifier uses.
    A provider outage must not become a wave of suppressed answers.
    """

    result: EntailmentResult | None
    usage: list[UsageRecord] = field(default_factory=list)


class EntailmentChecker:
    def __init__(self, llm: LLMProvider, *, prompt_name: str = prompts.ENTAIL) -> None:
        self._llm = llm
        self._prompt_name = prompt_name

    async def check(
        self, *, question: str, draft: str, context: AssembledContext
    ) -> EntailmentOutcome:
        if not draft.strip() or context.is_empty:
            return EntailmentOutcome(result=None)

        # The question comes first deliberately: it is the thing being judged
        # against, and burying it under a page of excerpts invites the model to
        # start assessing the excerpts instead.
        user_content = (
            f"# Question\n\n{question}\n\n"
            f"# Drafted answer\n\n{draft}\n\n"
            f"# Excerpts\n\n{context.text}"
        )

        try:
            response = await self._llm.complete(
                system=prompts.load(self._prompt_name),
                turns=[Turn(role="user", content=user_content)],
                max_tokens=ENTAILMENT_MAX_TOKENS,
                temperature=0.0,
            )
        except ProviderError as exc:
            log.warning("entailment_unavailable", error=str(exc))
            return EntailmentOutcome(result=None)

        usage = [UsageRecord.from_response("entail", response)]

        try:
            result = EntailmentResult.model_validate(extract_json(response.text))
        except (MalformedResponseError, ValueError) as exc:
            log.warning("entailment_unreadable", error=str(exc))
            return EntailmentOutcome(result=None, usage=usage)

        log.info("entailment_complete", verdict=result.verdict)
        return EntailmentOutcome(result=result, usage=usage)
