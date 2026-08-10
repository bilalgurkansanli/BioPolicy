"""Recovering a profile batch that was cut off at the token ceiling.

This failure has now happened twice on real documents. A batch containing a
coverage table emits one entry per sub-limit, each carrying a verbatim quote,
and runs past `PROFILE_MAX_TOKENS`. The reply is truncated mid-object, the JSON
does not parse, and the whole batch is discarded.

What that costs is specific rather than general: the model emits entries in
document order, so the batch most likely to be long is the first one — the page
carrying the schedule — and that page is also where `insured`, `policy_period`
and `territorial_scope` live. On the AXA policy the discarded reply was 8,132
characters beginning `{"entries": [{"field": "insured"`, and the profile came
back reporting those three slots as absent from a document that states all of
them on page one.

Raising the ceiling was the previous fix (2000 -> 4000) and it lost again.
Salvage ends the race by making the failure partial instead of total.
"""

from __future__ import annotations

from api.generation.profile import _salvage_entries

COMPLETE = """{"entries": [
  {"field": "insured", "label": "", "value": "ÖRNEK SİGORTALI", "chunk_id": "C1",
   "quote": "Sigortalının Adı Soyadı ÖRNEK SİGORTALI"},
  {"field": "policy_period", "label": "", "value": "07/08/2026 – 07/08/2027",
   "chunk_id": "C1", "quote": "Başlangıç Tarihi: : 07/08/2026"}
]}"""

# The same reply, cut off inside the third entry's quote.
TRUNCATED = """{"entries": [
  {"field": "insured", "label": "", "value": "ÖRNEK SİGORTALI", "chunk_id": "C1",
   "quote": "Sigortalının Adı Soyadı ÖRNEK SİGORTALI"},
  {"field": "policy_period", "label": "", "value": "07/08/2026 – 07/08/2027",
   "chunk_id": "C1", "quote": "Başlangıç Tarihi: : 07/08/2026"},
  {"field": "sub_limit", "label": "BİNA YANGIN", "value": "3.630.000,00 TL",
   "chunk_id": "C1", "quote": "*BİNA YANGIN 3.6"""


def test_the_entries_before_the_cut_survive() -> None:
    entries = _salvage_entries(TRUNCATED)

    assert [entry.field for entry in entries] == ["insured", "policy_period"]
    assert entries[0].value == "ÖRNEK SİGORTALI"


def test_the_entry_the_cut_landed_in_is_dropped_not_repaired() -> None:
    """No brace is appended and no string is closed. A half-read sub-limit is a
    wrong number, which is worse than a missing one in a document about money."""
    entries = _salvage_entries(TRUNCATED)

    assert all(entry.field != "sub_limit" for entry in entries)


def test_a_complete_reply_is_unaffected() -> None:
    """Salvage runs only after the normal parse fails, but it must not disagree
    with it when both can read the same text."""
    assert len(_salvage_entries(COMPLETE)) == 2


def test_the_wrapper_object_is_not_mistaken_for_an_entry() -> None:
    """`{"entries": [...]}` is balanced and parses; it is simply not an entry,
    and validation is what rejects it rather than a brace-counting heuristic."""
    entries = _salvage_entries('{"entries": []}')

    assert entries == []


def test_braces_inside_a_quoted_span_do_not_break_the_scan() -> None:
    """Policy text contains braces rarely but does contain escaped quotes often,
    and a scanner that ignored string state would split an entry in half."""
    text = (
        '{"entries": [{"field": "exclusion", "label": "Kasıt", '
        '"value": "kapsam dışı", "chunk_id": "C2", '
        '"quote": "Sigortalının \\"kasıtlı\\" hareketi {istisna}"}]}'
    )

    entries = _salvage_entries(text)

    assert len(entries) == 1
    assert "kasıtlı" in entries[0].quote


def test_prose_around_the_json_is_ignored() -> None:
    """Some replies open with a sentence before the object."""
    text = (
        'İşte çıkarım:\n{"entries": [{"field": "insured", "label": "", '
        '"value": "X", "chunk_id": "C1", "quote": "Sigortalı X"}]}'
    )

    assert len(_salvage_entries(text)) == 1


def test_a_reply_with_nothing_recoverable_yields_nothing() -> None:
    """The caller then reports the batch as failed, which is the honest outcome
    and the one that makes the interface withhold its 'not in this document'
    list."""
    assert _salvage_entries('{"entries": [{"field": "insu') == []
    assert _salvage_entries("provider returned prose only") == []
