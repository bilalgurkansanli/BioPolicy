"""Self-verification — Section 7.3.

A second, cheap pass over a drafted answer. It decomposes the draft into atomic
claims, marks each against the retrieved excerpts, and produces a groundedness
ratio that decides whether the answer is served, served with a warning, or
withheld.

## The verifier is not shown the question

This is the design decision that makes the pass worth running at all.

Given the original question, a verifier drifts toward agreement. It starts
assessing whether the answer *responds well* — which is a different property
from whether the answer is *supported*, and a fluent, on-topic, entirely
invented answer scores highly on the first while failing the second. Withholding
the question forces the only question we actually want answered: do these
excerpts say this?

## It is a second opinion, not a second attempt

The verifier never rewrites the answer. It only scores it. Letting it edit would
reintroduce, in the checking layer, exactly the generation behaviour the
checking layer exists to catch.
"""

from __future__ import annotations

from api.constants import GROUNDEDNESS_SERVE, GROUNDEDNESS_WARN
from api.generation import prompts
from api.generation.llm import (
    LLMProvider,
    MalformedResponseError,
    ProviderError,
    Turn,
    extract_json,
)
from api.generation.schemas import VerificationResult
from api.logging_config import get_logger
from api.retrieval.context import AssembledContext

log = get_logger(__name__)

# The verifier emits short structured verdicts, never prose. Capping output
# keeps a cheap pass cheap — this runs on every served answer.
VERIFIER_MAX_TOKENS = 900


class Verifier:
    def __init__(self, llm: LLMProvider, *, max_tokens: int = VERIFIER_MAX_TOKENS) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        self.prompt_version = prompts.VERIFY

    async def verify(self, *, draft: str, context: AssembledContext) -> VerificationResult | None:
        """Score a draft against the excerpts.

        Returns `None` when verification could not run — a provider failure or
        an unreadable response. `None` means *unknown*, not *failed*: the caller
        must not treat an absent score as a low one, or a provider outage would
        silently start suppressing correct answers.
        """
        if not draft.strip() or context.is_empty:
            return None

        # Note what is absent from this payload: the user's question.
        user_content = (
            f"# Source excerpts\n\n{context.text}\n\n# Drafted answer to check\n\n{draft}"
        )

        try:
            response = await self._llm.complete(
                system=prompts.load(prompts.VERIFY),
                turns=[Turn(role="user", content=user_content)],
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
        except ProviderError as exc:
            log.warning("verification_unavailable", error=str(exc))
            return None

        try:
            payload = extract_json(response.text)
            result = VerificationResult.model_validate(payload)
        except (MalformedResponseError, ValueError) as exc:
            log.warning("verification_unreadable", error=str(exc))
            return None

        log.info(
            "verification_complete",
            claims=len(result.claims),
            groundedness=round(result.groundedness, 3),
            unsupported=sum(1 for c in result.claims if c.support == "UNSUPPORTED"),
        )
        return result


def classify(groundedness: float | None) -> str:
    """Map a score onto the three service bands of Section 7.3.

    `None` (verification did not run) is treated as `serve`. The alternative —
    suppressing on an unknown score — would turn a provider outage into a
    product that refuses everything, and would do it in a way that looks like
    admirable caution rather than an incident.
    """
    if groundedness is None:
        return "serve"
    if groundedness >= GROUNDEDNESS_SERVE:
        return "serve"
    if groundedness >= GROUNDEDNESS_WARN:
        return "warn"
    return "suppress"
