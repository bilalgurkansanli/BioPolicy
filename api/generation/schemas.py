"""Structured shapes for generation and verification.

The model is required to emit `AnswerPayload` as JSON rather than prose. That is
not a stylistic preference — free text cannot be checked. `answer_found: false`
is a machine-readable refusal that the citation binder, the verifier and the
evaluation harness can all act on identically; "I'm afraid the document doesn't
appear to mention that" is a string somebody has to guess about.

Everything here is validated with pydantic, so a malformed model response fails
at the boundary with a specific error instead of producing an answer built on
half-parsed JSON.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]
ClaimSupport = Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]

# --- JSON Schemas for provider-enforced structured output ---------------------
#
# Claude Haiku 4.5 and Gemini both support constraining output to a schema, which
# is strictly better than asking for JSON in the prompt and hoping. The prompt
# still describes the shape — a model that understands *why* each field exists
# fills it in better — but the shape itself is now enforced by the provider.
#
# Written by hand rather than generated from the pydantic models. The API
# requires `additionalProperties: false` on every object and every property
# listed in `required`, which is not what pydantic emits by default; hand-written
# schemas make the contract visible at the point it matters instead of hiding it
# behind a post-processing step.

ANSWER_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answer_found": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["chunk_id", "quote"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer_found", "answer", "citations", "confidence", "caveats"],
    "additionalProperties": False,
}

VERIFICATION_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "support": {
                        "type": "string",
                        "enum": ["SUPPORTED", "PARTIAL", "UNSUPPORTED"],
                    },
                    "note": {"type": "string"},
                },
                "required": ["claim", "support", "note"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


ENTAILMENT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["ENTAILED", "RELATED_ONLY", "CONTRADICTED", "UNSURE"],
        },
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


class Citation(BaseModel):
    """A claim by the model that some chunk says something.

    Untrusted until bound. Both fields are checked in `api/generation/citations.py`:
    `chunk_id` must name a chunk that was actually in the prompt, and `quote`
    must actually appear in that chunk.
    """

    chunk_id: str = Field(description="A context id from the prompt, e.g. 'C2'.")
    quote: str = Field(description="Verbatim span from that chunk.")

    @field_validator("chunk_id")
    @classmethod
    def _normalise_id(cls, value: str) -> str:
        # Models write "C2", "[C2]", "c2" and " C2 " interchangeably. Normalising
        # here means the binder's lookup is exact and a formatting quirk never
        # masquerades as a fabricated citation.
        return value.strip().strip("[]").upper()


class AnswerPayload(BaseModel):
    """Exactly what the answering model must return."""

    answer_found: bool
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Confidence = "medium"
    caveats: list[str] = Field(default_factory=list)


class BoundCitation(BaseModel):
    """A citation that survived binding, resolved to real document coordinates.

    Page and bbox come from *our* record of the chunk, never from the model.
    That is what makes the citation chip in the UI trustworthy enough to be
    clickable.
    """

    chunk_id: UUID
    context_id: str
    quote: str
    page: int
    """Where the chunk starts. What the citation chip shows."""

    page_end: int
    """Where the chunk ends, which is not always where it starts.

    A chunk can run past a page break, and the quote can be on the far side of
    it — `page` alone sent the viewer looking on the wrong sheet, where it found
    nothing and fell back to highlighting the whole page. The range is what lets
    it look everywhere the quote could possibly be, and nowhere it could not.
    """

    section_path: str
    bbox: dict[str, float] | None = None
    exact: bool = True
    """False when the quote matched fuzzily — normal for OCR'd pages."""


class DroppedCitation(BaseModel):
    context_id: str
    quote: str
    reason: Literal["unknown_chunk", "quote_not_found"]


class ClaimVerdict(BaseModel):
    claim: str
    support: ClaimSupport
    note: str = ""


class EntailmentResult(BaseModel):
    """Whether the excerpts settle the question, rather than merely touch it."""

    verdict: Literal["ENTAILED", "RELATED_ONLY", "CONTRADICTED", "UNSURE"]
    reason: str = ""

    @property
    def licenses_the_answer(self) -> bool:
        """Only an outright entailment does.

        `UNSURE` is deliberately on the permissive side of this line while
        `RELATED_ONLY` is not: the first is the checker admitting it cannot
        tell, and suppressing on it would let a weak checker quietly become a
        censor. The second is a positive finding that a step was taken which the
        document does not license.
        """
        return self.verdict in ("ENTAILED", "UNSURE")


class VerificationResult(BaseModel):
    """Output of the self-verification pass."""

    claims: list[ClaimVerdict] = Field(default_factory=list)

    @property
    def groundedness(self) -> float:
        """supported / total, with PARTIAL counting as a half.

        A claim the verifier could only partially support is genuinely between
        the two states, and collapsing it to either extreme throws away the
        distinction the verifier was asked to make.
        """
        if not self.claims:
            # No claims extracted means nothing was verified. Returning 1.0
            # would let an unverifiable answer through the top threshold, so an
            # empty verification is treated as maximally unverified.
            return 0.0
        score = sum(
            1.0 if c.support == "SUPPORTED" else 0.5 if c.support == "PARTIAL" else 0.0
            for c in self.claims
        )
        return score / len(self.claims)


class GroundedAnswer(BaseModel):
    """The final, user-facing result after every check has run."""

    answer: str
    refused: bool
    citations: list[BoundCitation] = Field(default_factory=list)
    dropped_citations: list[DroppedCitation] = Field(default_factory=list)
    confidence: Confidence = "medium"
    caveats: list[str] = Field(default_factory=list)
    groundedness: float | None = None
    verified: bool = False
    """False when verification was disabled or did not run."""

    entailment: Literal["ENTAILED", "RELATED_ONLY", "CONTRADICTED", "UNSURE"] | None = None
    """What the entailment check concluded, or `None` when it did not run."""

    suppressed: bool = False
    """True when an answer existed but was withheld.

    This is a caught hallucination. It is counted in the evaluation report
    rather than hidden, because the rate at which this fires is one of the
    numbers that makes the product's claim credible.
    """

    suppression_reason: Literal["no_valid_citations", "low_groundedness", "not_entailed"] | None = (
        None
    )
