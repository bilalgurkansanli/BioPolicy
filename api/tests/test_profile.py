"""Typed extraction.

The assertions worth having here are about the two things that separate this
from asking a model to summarise a policy: an entry is only shown when its quote
survives binding, and a slot is only reported absent when nothing *survived*
filling it. The second follows from the first, and getting it backwards —
deriving absence from what the model claimed rather than from what was verified
— would produce a profile that confidently states a document is silent on
something it actually covers.
"""

from __future__ import annotations

import json

from api.generation.profile import (
    PROFILE_FIELDS,
    ProfileExtractor,
)
from api.tests.fakes import FailingLLM, ScriptedLLM
from api.tests.test_context import chunk

QUAKE = (
    "Madde 3.1 — Deprem teminatı, konutun ana yapısında oluşan hasarları "
    "1.800.000 TL limitine kadar karşılar."
)
WAIT = "Madde 5.2 — Doğum teminatı için bekleme süresi on iki aydır."


def payload(*entries: dict[str, str]) -> str:
    return json.dumps({"entries": list(entries)}, ensure_ascii=False)


def entry(
    *,
    field: str = "sub_limit",
    label: str = "Deprem",
    value: str = "1.800.000 TL",
    chunk_id: str = "C1",
    quote: str = "1.800.000 TL limitine kadar",
) -> dict[str, str]:
    return {
        "field": field,
        "label": label,
        "value": value,
        "chunk_id": chunk_id,
        "quote": quote,
    }


def extractor(*responses: str, **kwargs: object) -> tuple[ProfileExtractor, ScriptedLLM]:
    """A sweep wired to canned responses, one batch at a time.

    `concurrency=1` is a property of the *fake*, not of the thing under test.
    `ScriptedLLM` hands back its responses in call order, so with batches in
    flight together "the second response" stops meaning "the second batch" and
    any assertion tying a payload to a particular chunk becomes a coin flip.

    The production default stays concurrent, and nothing about correctness rests
    on the ordering: each batch assembles and binds against its own disjoint
    chunks, and `asyncio.gather` returns results in argument order however they
    interleaved.
    """
    llm = ScriptedLLM(*responses)
    kwargs.setdefault("concurrency", 1)
    return ProfileExtractor(llm, **kwargs), llm  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# the happy path
# -----------------------------------------------------------------------------


async def test_entry_survives_binding_and_carries_document_coordinates() -> None:
    sweep, _ = extractor(payload(entry()))

    profile = (await sweep.extract([chunk(QUAKE, page=4, section="Madde 3")])).profile

    assert len(profile.entries) == 1
    found = profile.entries[0]
    assert found.field == "sub_limit"
    assert found.label == "Deprem"
    assert found.value == "1.800.000 TL"

    # Page and section come from our record of the chunk, never from the model —
    # that is what makes the entry clickable rather than merely plausible.
    assert found.citation.page == 4
    assert found.citation.section_path == "Madde 3"
    assert found.citation.exact is True
    assert profile.dropped == 0


async def test_the_question_never_reaches_the_prompt() -> None:
    """A sweep has no question, and the prompt must not imply one.

    If a question ever leaked in here the extraction would quietly become
    retrieval, and the slots would fill with whatever was relevant to it.
    """
    sweep, llm = extractor(payload(entry()))
    await sweep.extract([chunk(QUAKE)])

    assert "# Excerpts from the document" in llm.payloads[0]
    assert "# Question" not in llm.payloads[0]


# -----------------------------------------------------------------------------
# binding, and what it discards
# -----------------------------------------------------------------------------


async def test_quote_absent_from_the_chunk_is_dropped() -> None:
    sweep, _ = extractor(payload(entry(quote="4.500.000 TL limitine kadar")))

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert profile.entries == []
    assert profile.dropped == 1


async def test_unknown_chunk_id_is_dropped() -> None:
    """One chunk was sent, so C7 names something the model was never shown."""
    sweep, _ = extractor(payload(entry(chunk_id="C7")))

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert profile.entries == []
    assert profile.dropped == 1


async def test_entry_with_an_empty_value_is_dropped() -> None:
    """A real citation attached to nothing renders as a blank row."""
    sweep, _ = extractor(payload(entry(value="   ")))

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert profile.entries == []
    assert profile.dropped == 1


async def test_absence_is_derived_after_binding_not_from_the_claim() -> None:
    """The load-bearing assertion of this module.

    The model claimed a sub-limit and the claim failed binding. The slot must
    therefore report as absent — deriving `absent` from what the model said
    would leave it filled, and the interface would show a slot with no entry
    under it.
    """
    sweep, _ = extractor(payload(entry(quote="a quote that appears nowhere at all")))

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert "sub_limit" in profile.absent
    assert set(profile.absent) == set(PROFILE_FIELDS)


async def test_a_filled_slot_is_not_reported_absent() -> None:
    sweep, _ = extractor(payload(entry()))

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert "sub_limit" not in profile.absent
    assert "exclusion" in profile.absent


async def test_empty_document_reports_every_slot_absent_without_calling_anything() -> None:
    sweep, llm = extractor()

    profile = (await sweep.extract([])).profile

    assert llm.call_count == 0
    assert list(profile.absent) == list(PROFILE_FIELDS)


# -----------------------------------------------------------------------------
# batching
# -----------------------------------------------------------------------------


async def test_ids_restart_per_batch_and_still_bind_to_the_right_chunk() -> None:
    """Each batch is assembled independently, so `C2` means something different
    in the second call than in the first. Binding happens per batch, against the
    context that produced it, which is what keeps that from being a collision.
    """
    chunks = [
        chunk("Clause one, about nothing."),
        chunk(QUAKE),
        chunk("Clause three."),
        chunk(WAIT),
    ]
    sweep, llm = extractor(
        payload(entry(chunk_id="C2")),
        payload(
            entry(
                field="waiting_period",
                label="Doğum",
                value="on iki ay",
                chunk_id="C2",
                quote="bekleme süresi on iki aydır",
            )
        ),
        batch_chunks=2,
    )

    profile = (await sweep.extract(chunks)).profile

    assert llm.call_count == 2
    assert profile.dropped == 0
    # `C2` in batch one is the earthquake chunk; `C2` in batch two is the
    # waiting-period chunk. Both resolved to their own real UUIDs.
    bound = {e.field: e.citation.chunk_id for e in profile.entries}
    assert bound["sub_limit"] == chunks[1].chunk_id
    assert bound["waiting_period"] == chunks[3].chunk_id


async def test_repeats_across_batches_collapse_to_one_entry() -> None:
    """Two batches both covering the coverage table report the same limit."""
    chunks = [chunk(QUAKE), chunk(QUAKE)]
    sweep, _ = extractor(payload(entry()), payload(entry()), batch_chunks=1)

    profile = (await sweep.extract(chunks)).profile

    assert len(profile.entries) == 1


async def test_singular_fields_keep_only_one_entry() -> None:
    """A document has one insured party, however many batches mention it."""
    text = "Sigortalı: Ayşe Yılmaz, Bağdat Caddesi No 12, İstanbul."
    chunks = [chunk(text), chunk(text)]
    sweep, _ = extractor(
        payload(entry(field="insured", label="", value="Ayşe Yılmaz", quote="Sigortalı: Ayşe")),
        payload(
            entry(
                field="insured",
                label="",
                value="Ayşe Yılmaz, Bağdat Caddesi No 12",
                quote="Bağdat Caddesi No 12",
            )
        ),
        batch_chunks=1,
    )

    profile = (await sweep.extract(chunks)).profile

    assert len(profile.by_field("insured")) == 1


# -----------------------------------------------------------------------------
# coverage, and telling "nobody looked" from "the document is silent"
# -----------------------------------------------------------------------------


async def test_a_failed_batch_is_counted_and_does_not_fail_the_profile() -> None:
    chunks = [chunk(QUAKE), chunk(WAIT)]
    llm = FailingLLM()
    sweep = ProfileExtractor(llm, batch_chunks=1)

    profile = (await sweep.extract(chunks)).profile

    assert profile.batches_failed == 2
    assert profile.entries == []
    # Every slot is empty, but not because the document is silent — and
    # `complete` is what stops the interface from saying otherwise.
    assert profile.complete is False


async def test_unreadable_json_counts_as_a_failed_batch() -> None:
    sweep, _ = extractor("this is not JSON at all")

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert profile.batches_failed == 1
    assert profile.complete is False


async def test_sweeping_part_of_a_document_is_reported_as_incomplete() -> None:
    chunks = [chunk(QUAKE) for _ in range(6)]
    sweep, _ = extractor(payload(entry()), batch_chunks=2, max_chunks=2)

    profile = (await sweep.extract(chunks)).profile

    assert profile.chunks_seen == 2
    assert profile.chunks_total == 6
    assert profile.complete is False


async def test_a_full_clean_sweep_is_complete() -> None:
    sweep, _ = extractor(payload(entry()))

    profile = (await sweep.extract([chunk(QUAKE)])).profile

    assert profile.chunks_seen == profile.chunks_total == 1
    assert profile.batches_failed == 0
    assert profile.complete is True


# -----------------------------------------------------------------------------
# cost accounting
# -----------------------------------------------------------------------------


async def test_every_batch_is_billed_including_one_whose_entries_were_dropped() -> None:
    """A batch whose output was discarded still cost money.

    Recording only the batches that produced usable entries would understate
    spend exactly when the model is behaving worst, which is when the budget
    breaker most needs to see it.
    """
    sweep, _ = extractor(
        payload(entry()),
        payload(entry(quote="nowhere near the text of this chunk")),
        batch_chunks=1,
    )

    outcome = await sweep.extract([chunk(QUAKE), chunk(QUAKE)])

    assert [u.operation for u in outcome.usage] == ["profile", "profile"]
    assert outcome.cost_relevant_tokens > 0
    assert outcome.profile.dropped == 1
