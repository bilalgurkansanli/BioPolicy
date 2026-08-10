"""Typed extraction — reading the whole document into a fixed shape.

Everything else in this system answers a question. This does not. It sweeps the
entire document and fills a fixed set of slots, because the person who most
needs to know what their policy says is the person who does not know what to ask
about it. A chatbot requires you to already know the question; a schema does
not.

Three properties make this different from asking a general-purpose model to
"summarise my policy", and all three are the same properties the answering path
already has:

**Every entry carries a bound citation.** The model names an excerpt id and
quotes a span; the quote is checked against that excerpt's actual text before
the entry is shown. An entry whose citation fails is discarded, exactly as an
answer's would be. What survives is clickable, and clicking it puts a highlight
on the clause in the PDF.

**Absence is derived, never asserted.** The model is not asked "does this policy
have a waiting period?" — it is asked to report waiting periods it can see, and
a slot nobody filled is reported as empty *by us*, from the count. A model
asserting "no waiting period" is a claim about a whole document from a model
that saw one slice of it. A count of zero across every slice is arithmetic.

**Coverage is reported, not assumed.** The sweep has a chunk ceiling, and a
document larger than it is profiled partially. When that happens the profile
says so rather than presenting a partial reading as a complete one — the same
rule the evaluation report follows about its own gaps.

## Why batches, and why binding still works

The document does not fit in one prompt, so chunks are swept in batches. Each
batch is assembled by `retrieval.context.assemble`, which stamps `[C1]`…`[Cn]`
onto that batch's chunks — ids restart per batch, and that is fine, because a
batch is bound immediately against the context it was generated from. What comes
out the far side is a `BoundCitation` carrying the chunk's real UUID, page range
and bbox, so nothing downstream needs to know batches ever existed.

A batch whose provider call fails does not fail the profile. It is counted, and
the count is reported, because a slot that is empty because nobody looked is not
the same as a slot that is empty because the document is silent — and conflating
those two is the exact error this module exists to avoid.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from api.generation import prompts
from api.generation.citations import normalise, quote_appears_in
from api.generation.llm import (
    LLMProvider,
    MalformedResponseError,
    ProviderError,
    Turn,
    UsageRecord,
    extract_json,
)
from api.generation.schemas import BoundCitation
from api.logging_config import get_logger
from api.retrieval.context import MAX_CONTEXT_TOKENS, assemble
from api.retrieval.types import RetrievedChunk

log = get_logger(__name__)

# The slots. Order is presentation order in the interface: who and what is
# covered, then what is covered, then everything that cuts it down. A reader
# scanning for the catch should find the catch grouped together.
ProfileField = Literal[
    "insured",
    "policy_period",
    "territorial_scope",
    "covered_peril",
    "exclusion",
    "sub_limit",
    "deductible",
    "waiting_period",
    "notification_deadline",
]

PROFILE_FIELDS: tuple[ProfileField, ...] = (
    "insured",
    "policy_period",
    "territorial_scope",
    "covered_peril",
    "sub_limit",
    "deductible",
    "waiting_period",
    "notification_deadline",
    "exclusion",
)

# Fields that can only sensibly have one value. Used to keep the interface from
# rendering three different "insured" rows when three batches each found the
# same party worded slightly differently.
SINGULAR_FIELDS: frozenset[str] = frozenset({"insured", "policy_period", "territorial_scope"})

# How many chunks one prompt gets. Larger batches mean fewer calls and cheaper
# extraction, but a model asked to fill nine slots from thirty clauses starts
# skipping some. Eight matches the answering path's context window, which is the
# only figure here with an evaluation behind it.
PROFILE_BATCH_CHUNKS = 8

# Hard ceiling on the sweep, in chunks. A document past this is profiled
# partially and *says so*; sweeping everything would make the cost of one
# profile unbounded, and this project's rule is that an operation has a knowable
# maximum cost.
#
# Raised from 96 after a real 27-page AXA policy came in at 132 chunks and was
# read three-quarters through — enough to look complete and not be. 160 covers
# it with room, and the ceiling is still a ceiling: 20 batches at ~$0.005 is
# about $0.10 for a profile, charged once per document and then cached.
PROFILE_MAX_CHUNKS = 160

# Output cap per batch.
#
# Set to 2000 on the first pass, on the reasoning that nine slots with a quote
# each fits comfortably. The first live run against a four-page sample disproved
# it: a batch containing the coverage table emitted 4388 characters and was
# still cut off mid-object, because a table of fourteen sub-limits is fourteen
# entries and each one carries a verbatim quote. The truncated JSON failed to
# parse and the whole batch was lost — including `insured`, `policy_period` and
# `territorial_scope`, which the response had already produced.
#
# That failure is loud rather than silent (the batch counts as failed and the
# interface says coverage is incomplete), which is the only reason it was
# diagnosable. But the right cap is one the common case does not hit.
#
# It lost again anyway. A real AXA policy emitted 8,132 characters and was cut
# off at 4000, taking `insured`, `policy_period` and `territorial_scope` with
# it. Raising the number is a race against whichever document has the longest
# schedule, so the cap moved to 6000 *and* `_salvage_entries` now recovers the
# complete entries from a truncated reply. The salvage is the actual fix; this
# number only decides how often it is needed.
PROFILE_MAX_TOKENS = 6000

# Batches in flight at once. Bounded because every one of them is a billable
# call against the same rate limit, and an unbounded gather over a long document
# is the fastest way to turn a profile into a 429.
PROFILE_CONCURRENCY = 3


PROFILE_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": list(PROFILE_FIELDS)},
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "chunk_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["field", "label", "value", "chunk_id", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}


class ProfileEntryPayload(BaseModel):
    """One slot filled by the model. Untrusted until its quote is bound."""

    field: ProfileField
    label: str = ""
    value: str
    chunk_id: str
    quote: str

    @field_validator("chunk_id")
    @classmethod
    def _normalise_id(cls, value: str) -> str:
        # Same normalisation as `schemas.Citation`: models write "C2", "[C2]",
        # "c2" and " C2 " interchangeably, and a formatting quirk must never
        # look like a fabricated id.
        return value.strip().strip("[]").upper()


class ProfilePayload(BaseModel):
    """Exactly what one batch must return."""

    entries: list[ProfileEntryPayload] = Field(default_factory=list)


def _salvage_entries(text: str) -> list[ProfileEntryPayload]:
    """Recover the complete entries from a reply that was cut off mid-object.

    Scans for balanced `{...}` spans and keeps the ones that parse *and* satisfy
    the entry schema. The object the truncation landed inside is unbalanced and
    is simply never closed, so it is skipped — there is no partial entry to
    misread, and nothing is reconstructed or guessed.

    Deliberately not a JSON repair: no brace is appended, no string is closed.
    An entry that arrived whole is used, an entry that did not is gone, and the
    caller still reports the batch as degraded.
    """
    entries: list[ProfileEntryPayload] = []
    # Every `{` seen and not yet closed. A stack rather than a depth counter,
    # because the entries are *nested inside* the `{"entries": [...]}` wrapper —
    # and on a truncated reply that wrapper never closes, so anything keyed off
    # returning to depth zero finds nothing at all. That was the first version,
    # and the tests caught it.
    open_at: list[int] = []
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            open_at.append(index)
        elif char == "}" and open_at:
            start = open_at.pop()
            try:
                entries.append(ProfileEntryPayload.model_validate_json(text[start : index + 1]))
            except ValidationError:
                # The wrapper, or any object that is not an entry. Validation
                # decides, not brace-counting: this is a best-effort pass over a
                # broken response and it must never invent an entry.
                pass

    return entries


class ProfileEntry(BaseModel):
    """An entry that survived binding, resolved to real document coordinates."""

    field: ProfileField
    label: str
    value: str
    citation: BoundCitation


class PolicyProfile(BaseModel):
    """The whole document, read into the schema.

    `absent` is the half of this object that a chatbot cannot produce: the slots
    the document does not fill. It is computed from the entry counts rather than
    claimed by a model, which is what makes it worth showing.
    """

    entries: list[ProfileEntry] = Field(default_factory=list)

    absent: list[ProfileField] = Field(default_factory=list)
    """Slots no surviving entry filled. Empty because the document is silent."""

    chunks_seen: int = 0
    chunks_total: int = 0

    batches_failed: int = 0
    """Batches whose provider call or JSON failed. Their slots were not read."""

    dropped: int = 0
    """Entries discarded because their quote did not appear in the chunk named."""

    model: str = ""
    prompt_version: str = ""

    @property
    def complete(self) -> bool:
        """True when every chunk was read and every batch came back.

        The interface uses this to decide between "this document does not
        mention X" and "X was not found in the part of the document that was
        read" — a distinction that is the whole point of publishing coverage.
        """
        return self.chunks_seen >= self.chunks_total and self.batches_failed == 0

    def by_field(self, name: ProfileField) -> list[ProfileEntry]:
        return [e for e in self.entries if e.field == name]


@dataclass(slots=True)
class ProfileOutcome:
    profile: PolicyProfile
    usage: list[UsageRecord] = dataclass_field(default_factory=list)

    @property
    def cost_relevant_tokens(self) -> int:
        return sum(u.input_tokens + u.output_tokens for u in self.usage)


class ProfileExtractor:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        batch_chunks: int = PROFILE_BATCH_CHUNKS,
        max_chunks: int = PROFILE_MAX_CHUNKS,
        max_tokens: int = PROFILE_MAX_TOKENS,
        concurrency: int = PROFILE_CONCURRENCY,
        prompt_name: str = prompts.PROFILE,
    ) -> None:
        self._llm = llm
        self._batch_chunks = batch_chunks
        self._max_chunks = max_chunks
        self._max_tokens = max_tokens
        self._concurrency = concurrency
        self._prompt_name = prompt_name

    async def extract(self, chunks: list[RetrievedChunk]) -> ProfileOutcome:
        """Sweep the document and return the filled schema.

        Chunks arrive in document order, not relevance order — this is a sweep,
        not a search, and reading a policy back to front would split clauses
        from the tables that qualify them.
        """
        total = len(chunks)
        swept = chunks[: self._max_chunks]

        if not swept:
            return ProfileOutcome(
                profile=PolicyProfile(
                    absent=list(PROFILE_FIELDS),
                    chunks_total=total,
                    model=self._llm.model,
                    prompt_version=self._prompt_name,
                )
            )

        batches = [
            swept[i : i + self._batch_chunks] for i in range(0, len(swept), self._batch_chunks)
        ]

        semaphore = asyncio.Semaphore(self._concurrency)

        async def run(batch: list[RetrievedChunk]) -> _BatchResult:
            async with semaphore:
                return await self._one_batch(batch)

        results = await asyncio.gather(*(run(batch) for batch in batches))

        entries: list[ProfileEntry] = []
        usage: list[UsageRecord] = []
        dropped = 0
        failed = 0
        model = self._llm.model

        for result in results:
            entries.extend(result.entries)
            usage.extend(result.usage)
            dropped += result.dropped
            failed += int(result.failed)
            if result.model:
                model = result.model

        merged = _merge(entries)
        filled = {e.field for e in merged}

        profile = PolicyProfile(
            entries=merged,
            absent=[f for f in PROFILE_FIELDS if f not in filled],
            chunks_seen=len(swept),
            chunks_total=total,
            batches_failed=failed,
            dropped=dropped,
            model=model,
            prompt_version=self._prompt_name,
        )

        log.info(
            "profile_extracted",
            entries=len(merged),
            dropped=dropped,
            batches=len(batches),
            batches_failed=failed,
            chunks_seen=len(swept),
            chunks_total=total,
        )
        return ProfileOutcome(profile=profile, usage=usage)

    async def _one_batch(self, batch: list[RetrievedChunk]) -> _BatchResult:
        context = assemble(
            batch,
            max_chunks=len(batch),
            max_tokens=MAX_CONTEXT_TOKENS,
        )
        if context.is_empty:
            return _BatchResult()

        try:
            response = await self._llm.complete(
                system=prompts.load(self._prompt_name),
                turns=[Turn(role="user", content=_user_turn(context.text))],
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
        except ProviderError as exc:
            log.warning("profile_batch_unavailable", error=str(exc))
            return _BatchResult(failed=True)

        usage = [UsageRecord.from_response("profile", response)]

        try:
            payload = ProfilePayload.model_validate(extract_json(response.text))
        except (MalformedResponseError, ValueError) as exc:
            # A truncated response is not an empty one. The model emits entries
            # in order, so a reply cut off at the token ceiling still contains
            # every complete entry before the cut — and losing them is expensive
            # in a specific way: the first batch is where `insured`,
            # `policy_period` and `territorial_scope` live, so dropping it makes
            # a document look like it never states its own dates.
            #
            # Raising `PROFILE_MAX_TOKENS` was the earlier fix (2000 -> 4000) and
            # it is a race rather than an answer: a real AXA policy emitted 8,132
            # characters and was cut off again. Salvaging what arrived ends the
            # race, because the failure mode stops being all-or-nothing.
            salvaged = _salvage_entries(response.text)
            if not salvaged:
                log.warning("profile_batch_unreadable", error=str(exc))
                return _BatchResult(usage=usage, failed=True, model=response.model)

            log.warning(
                "profile_batch_salvaged",
                entries=len(salvaged),
                characters=len(response.text),
                error=str(exc)[:120],
            )
            payload = ProfilePayload(entries=salvaged)

        kept: list[ProfileEntry] = []
        dropped = 0
        available = context.by_id

        for item in payload.entries:
            chunk = available.get(item.chunk_id)
            if chunk is None:
                # Either invented, or naming a chunk trimmed for budget. Both
                # mean the model cited something it was not shown.
                #
                # Logged with the field, because the aggregate count is not
                # diagnosable: a policy came back with `policy_period` marked
                # absent from a page that prints its dates twice, and "dropped=1"
                # was the only trace. Which slot was lost, and why, is the whole
                # question.
                log.warning(
                    "profile_entry_dropped",
                    field=item.field,
                    reason="unknown_chunk",
                    chunk_id=item.chunk_id,
                )
                dropped += 1
                continue

            found, exact = quote_appears_in(item.quote, chunk.content)
            if not found:
                log.warning(
                    "profile_entry_dropped",
                    field=item.field,
                    reason="quote_not_found",
                    chunk_id=item.chunk_id,
                    quote=item.quote[:120],
                )
                dropped += 1
                continue

            if not item.value.strip():
                # A slot with a real citation and nothing in it renders as an
                # empty row. Drop it rather than show the reader a clause that
                # apparently says nothing.
                dropped += 1
                continue

            kept.append(
                ProfileEntry(
                    field=item.field,
                    label=item.label.strip(),
                    value=item.value.strip(),
                    citation=BoundCitation(
                        chunk_id=chunk.chunk_id,
                        context_id=item.chunk_id,
                        quote=item.quote,
                        # Page and geometry come from our record of the chunk,
                        # never from the model. This is what makes the entry
                        # clickable rather than merely plausible.
                        page=chunk.page_start,
                        page_end=chunk.page_end,
                        section_path=chunk.section_path,
                        bbox=chunk.bbox.as_dict() if chunk.bbox else None,
                        exact=exact,
                    ),
                )
            )

        if dropped:
            log.warning("profile_entries_dropped", dropped=dropped, kept=len(kept))

        return _BatchResult(entries=kept, usage=usage, dropped=dropped, model=response.model)


@dataclass(slots=True)
class _BatchResult:
    entries: list[ProfileEntry] = dataclass_field(default_factory=list)
    usage: list[UsageRecord] = dataclass_field(default_factory=list)
    dropped: int = 0
    failed: bool = False
    model: str = ""


def _merge(entries: list[ProfileEntry]) -> list[ProfileEntry]:
    """Collapse repeats across batches and order for presentation.

    Two batches that both cover the coverage table will both report the
    earthquake sub-limit. Deduplication is on the *content* of the entry —
    field, label, value — and not on the citation, because the same fact quoted
    from two different chunks is still one fact to the reader.

    Singular fields keep only their first surviving entry. A document has one
    insured party; three rows for it is a bug in the extraction showing through
    to the interface.
    """
    seen: set[tuple[str, str, str]] = set()
    singular_taken: set[str] = set()
    out: list[ProfileEntry] = []

    for entry in entries:
        key = (entry.field, normalise(entry.label), normalise(entry.value))
        if key in seen:
            continue
        if entry.field in SINGULAR_FIELDS:
            if entry.field in singular_taken:
                continue
            singular_taken.add(entry.field)
        seen.add(key)
        out.append(entry)

    order = {name: i for i, name in enumerate(PROFILE_FIELDS)}
    # Stable sort: within a field, entries keep the order the document put them
    # in, because a coverage list reads as a list and alphabetising it would
    # destroy the grouping the drafter chose.
    out.sort(key=lambda e: order.get(e.field, len(order)))
    return out


def _user_turn(context_text: str) -> str:
    return f"# Excerpts from the document\n\n{context_text}"
