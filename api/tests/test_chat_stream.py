"""The answering route, as the browser actually receives it.

Everything else in this suite tests a component. This tests the stream: the
order of the events, what each one carries, and — the reason it exists — that
the two paths through `done` produce the same shape. A field added to one and
not the other is read by the client as `undefined`, which renders as a missing
citation or a blank cost rather than as an error anyone would notice.
"""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.answer_cache import CachedAnswer
from api.auth import AuthenticatedUser, required_user
from api.deps import get_state
from api.generation.answerer import AnswerOutcome
from api.generation.schemas import BoundCitation, GroundedAnswer
from api.main import create_app
from api.retrieval.context import AssembledContext
from api.retrieval.floor import FloorVerdict
from api.retrieval.hybrid import RetrievalResult
from api.retrieval.types import RetrievedChunk

USER = uuid4()
DOCUMENT = uuid4()


def _chunk(context_id: str, page: int = 3) -> RetrievedChunk:
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        content="Madde 4.1 — Evcil hayvanların sigortalı eşyaya verdiği zararlar " * 6,
        content_type="text",
        page_start=page,
        page_end=page,
        section_path="Madde 4",
    )
    chunk.context_id = context_id
    return chunk


class _Retriever:
    def __init__(self, *, below_floor: bool) -> None:
        self.calls = 0
        self._below = below_floor

    async def retrieve(self, **_: object) -> RetrievalResult:
        self.calls += 1
        chunks = [_chunk("C1"), _chunk("C2", page=5)]
        return RetrievalResult(
            context=AssembledContext(chunks=chunks, text="…", token_count=120),
            candidates=chunks,
            search_query="evcil hayvan",
            floor=FloorVerdict(
                below=self._below,
                best_distance=0.51 if self._below else 0.28,
                keyword_hits=0,
                candidates=2,
            ),
        )


class _Answerer:
    """Records whether it was reached at all. That is the whole assertion for
    the floor: not that the refusal reads well, but that nothing was spent."""

    def __init__(self) -> None:
        self.calls = 0

    async def answer(self, **_: object) -> AnswerOutcome:
        self.calls += 1
        return AnswerOutcome(
            answer=GroundedAnswer(
                answer="Deprem teminatının limiti 1.800.000 TL.",
                refused=False,
                # A citation, because an answer without one is not cacheable and
                # several assertions below are about what gets stored.
                citations=[
                    BoundCitation(
                        chunk_id=uuid4(),
                        context_id="C1",
                        quote="1.800.000 TL",
                        page=3,
                        page_end=3,
                        section_path="Madde 2",
                        bbox=None,
                        exact=True,
                    )
                ],
            )
        )


class _Breaker:
    async def ensure_capacity(self) -> None: ...
    def note_spend(self, cost: float) -> None: ...


class _Quota:
    async def ensure_can_ask(self, user_id: object) -> None: ...


class _Pool:
    async def fetchrow(self, *_: object) -> dict[str, object]:
        return {"id": DOCUMENT, "user_id": USER, "detected_lang": "tr"}


class _Usage:
    async def record(self, **_: object) -> float:
        return 0.0


class _Conversations:
    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    async def ensure(self, **_: object) -> object:
        return uuid4()

    async def append_turn(self, **kwargs: Any) -> None:
        self.turns.append(kwargs)


class _Cache:
    """Misses unless handed a payload, and records what it was asked to store."""

    def __init__(self, hit: CachedAnswer | None = None) -> None:
        self.hit = hit
        self.stored: list[dict[str, Any]] = []

    async def get(self, **_: object) -> CachedAnswer | None:
        return self.hit

    async def put(self, *, payload: dict[str, Any], **_: object) -> None:
        self.stored.append(payload)


def _client(
    *,
    below_floor: bool = False,
    cache: _Cache | None = None,
    conversations: _Conversations | None = None,
) -> tuple[TestClient, _Retriever, _Answerer]:
    retriever = _Retriever(below_floor=below_floor)
    answerer = _Answerer()

    class _State:
        pool = _Pool()
        breaker = _Breaker()
        quota = _Quota()
        usage = _Usage()

    state = _State()
    state.conversations = conversations or _Conversations()  # type: ignore[attr-defined]
    state.answer_cache = cache or _Cache()  # type: ignore[attr-defined]
    state.retriever = retriever  # type: ignore[attr-defined]
    state.answerer = answerer  # type: ignore[attr-defined]

    app = create_app()
    app.dependency_overrides[get_state] = lambda: state
    app.dependency_overrides[required_user] = lambda: AuthenticatedUser(
        id=USER, email="tester@example.com", is_anonymous=False
    )
    return TestClient(app), retriever, answerer


def _events(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    response = client.post(
        "/api/chat",
        json={"document_id": str(DOCUMENT), "question": "Kedim koltuğu çizdi", "language": "tr"},
    )
    assert response.status_code == 200

    parsed: list[tuple[str, dict[str, Any]]] = []
    name: str | None = None
    for line in response.text.splitlines():
        if line.startswith("event:"):
            name = line.removeprefix("event:").strip()
        elif line.startswith("data:") and name:
            parsed.append((name, json.loads(line.removeprefix("data:").strip())))
    return parsed


# --- what retrieval reports ---------------------------------------------------


def test_retrieval_complete_carries_every_passage_that_reached_the_prompt() -> None:
    client, _, _ = _client(below_floor=False)
    events = dict(_events(client))

    considered = events["retrieval_complete"]["considered"]
    assert [c["context_id"] for c in considered] == ["C1", "C2"]
    assert considered[1]["page"] == 5


def test_a_snippet_is_a_label_rather_than_the_clause() -> None:
    """Long enough to recognise a passage, short enough that nobody reads the
    document in the sidebar instead of in the viewer."""
    client, _, _ = _client(below_floor=False)
    events = dict(_events(client))

    snippet = events["retrieval_complete"]["considered"][0]["snippet"]
    assert len(snippet) <= 181  # 180 plus the ellipsis
    assert snippet.endswith("…")
    assert "\n" not in snippet


# --- the floor ----------------------------------------------------------------


def test_below_the_floor_no_model_is_called() -> None:
    """The point of the floor, stated as an assertion about spend."""
    client, retriever, answerer = _client(below_floor=True)
    events = _events(client)

    assert retriever.calls == 1
    assert answerer.calls == 0
    assert dict(events)["done"]["cost_usd"] == 0.0


def test_the_floors_refusal_is_a_refusal_not_a_suppression() -> None:
    """Suppression means an answer existed and was withheld. Here none was ever
    drafted, and the eval's safety metrics count the two differently."""
    client, _, _ = _client(below_floor=True)
    done = dict(_events(client))["done"]

    assert done["refused"] is True
    assert done["suppressed"] is False
    assert done["suppression_reason"] is None
    assert done["citations"] == []


def test_the_refusal_arrives_after_the_evidence_that_justifies_it() -> None:
    """A refusal a user cannot inspect is one they have to take on trust."""
    client, _, _ = _client(below_floor=True)
    names = [name for name, _ in _events(client)]

    assert names.index("retrieval_complete") < names.index("done")
    assert "answering" not in names


def test_above_the_floor_the_model_is_called() -> None:
    client, _, answerer = _client(below_floor=False)
    _events(client)
    assert answerer.calls == 1


# --- the two paths agree ------------------------------------------------------


# Deliberately the shape `AnswerCache.put` really stores, extra keys included.
# The first version of this fixture held only the keys `done` sends, so the test
# below passed while the live cached path emitted two fields a fresh answer does
# not — the precise defect that test claims to prevent.
CACHED_PAYLOAD = {
    "conversation_id": None,
    "cached": None,
    "answer": "Deprem teminatının limiti 1.800.000 TL.",
    "refused": False,
    "suppressed": False,
    "suppression_reason": None,
    "confidence": "high",
    "caveats": [],
    "groundedness": 0.94,
    "verified": True,
    "entailment": None,
    "citations": [{"context_id": "C1", "quote": "1.800.000 TL", "page": 3}],
    "dropped_citations": 0,
    "cost_usd": 0.0031,
    "considered": [{"context_id": "C1", "page": 3, "snippet": "…"}],
    "prompt_version": "answer_v2",
    "model": "claude-haiku-4-5",
}


@pytest.mark.parametrize(
    "make",
    [
        lambda: _client(below_floor=False),
        lambda: _client(below_floor=True),
        lambda: _client(cache=_Cache(CachedAnswer(payload=dict(CACHED_PAYLOAD), served_before=4))),
    ],
    ids=["answered", "below_floor", "cached"],
)
def test_every_done_payload_has_identical_keys(make: Any) -> None:
    """The regression this file was written for. Three code paths build `done`,
    and a client reading a field only one of them sets sees `undefined`."""
    client, _, _ = make()
    done = dict(_events(client))["done"]

    assert set(done) == {
        "conversation_id",
        "cached",
        "answer",
        "refused",
        "suppressed",
        "suppression_reason",
        "confidence",
        "caveats",
        "groundedness",
        "verified",
        "entailment",
        "citations",
        "dropped_citations",
        "cost_usd",
    }


# --- the cache ----------------------------------------------------------------


def test_a_cache_hit_costs_nothing_and_says_so() -> None:
    """The honesty rule. An answer served in milliseconds for nothing must not
    look like one that was computed, or the latency and cost figures published
    in eval/report.md are quietly contradicted by the product itself."""
    cache = _Cache(CachedAnswer(payload=dict(CACHED_PAYLOAD), served_before=4))
    client, retriever, answerer = _client(cache=cache)

    done = dict(_events(client))["done"]

    assert done["cached"] == 4
    assert done["cost_usd"] == 0.0
    assert retriever.calls == 0  # not even the query embedding
    assert answerer.calls == 0


def test_a_cache_hit_still_shows_what_was_considered() -> None:
    """A replayed answer carries the same evidence a fresh one does."""
    cache = _Cache(CachedAnswer(payload=dict(CACHED_PAYLOAD), served_before=0))
    client, _, _ = _client(cache=cache)

    events = dict(_events(client))

    assert events["retrieval_complete"]["considered"][0]["context_id"] == "C1"
    assert "considered" not in events["done"]


def test_a_replayed_answer_keeps_its_citations_in_the_users_history() -> None:
    """The defect this catches shipped: the cached path passed an empty list.

    The same question then produced two different histories depending on whether
    it happened to hit — a stored turn with its clauses, or one with none — and
    nothing anywhere reported the difference.
    """
    conversations = _Conversations()
    client, _, _ = _client(
        cache=_Cache(CachedAnswer(payload=dict(CACHED_PAYLOAD), served_before=1)),
        conversations=conversations,
    )

    _events(client)

    assert len(conversations.turns) == 1
    stored = conversations.turns[0]
    assert [c["context_id"] for c in stored["citations"]] == ["C1"]
    # And the provenance of the answer being replayed, not of today's config.
    assert stored["prompt_version"] == "answer_v2"
    assert stored["model"] == "claude-haiku-4-5"


def test_a_fresh_answer_says_it_is_not_cached() -> None:
    client, _, _ = _client()
    assert dict(_events(client))["done"]["cached"] is None


def test_a_fresh_answer_is_stored_with_its_passages() -> None:
    cache = _Cache()
    client, _, _ = _client(cache=cache)

    _events(client)

    assert len(cache.stored) == 1
    assert [c["context_id"] for c in cache.stored[0]["considered"]] == ["C1", "C2"]


def test_a_floor_refusal_is_not_stored() -> None:
    """`is_cacheable` rejects refusals, and the floor's is the cheapest answer
    in the system anyway — there is nothing to save."""
    cache = _Cache()
    client, _, _ = _client(below_floor=True, cache=cache)

    _events(client)

    assert cache.stored == []


def test_the_shape_survives_a_round_trip_through_json() -> None:
    """SSE data is a string on the wire; anything not JSON-serialisable would
    fail inside the generator and surface only as a truncated stream."""
    client, _, _ = _client(below_floor=False)
    for _name, payload in _events(client):
        assert json.loads(json.dumps(payload, ensure_ascii=False)) == cast(Any, payload)
