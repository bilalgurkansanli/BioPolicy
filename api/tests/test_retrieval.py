"""Hybrid retrieval: RRF fusion and the query pipeline around it."""

from __future__ import annotations

from uuid import uuid4

import pytest

from api.constants import RRF_K
from api.generation.llm import Turn
from api.retrieval.fusion import fuse, reciprocal_rank_fusion
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import to_pgvector
from api.retrieval.types import RetrievedChunk
from api.tests.fakes import FailingLLM, ScriptedLLM, StubEmbedder, StubStore

DOC = uuid4()
USER = uuid4()


def hit(
    name: str, *, page: int = 1, vector: int | None = None, keyword: int | None = None
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        content=name,
        content_type="text",
        page_start=page,
        page_end=page,
        section_path="Madde 1",
        vector_rank=vector,
        keyword_rank=keyword,
    )


# -----------------------------------------------------------------------------
# fusion
# -----------------------------------------------------------------------------


class TestReciprocalRankFusion:
    def test_agreement_across_arms_beats_a_single_strong_hit(self) -> None:
        """The central property, and the reason RRF is the right choice here.

        Two independent retrieval methods agreeing is real evidence. One arm's
        confidence, however high, is not.
        """
        both = hit("agreed-by-both", vector=3, keyword=3)
        one = hit("top-of-one-arm", vector=1)

        ranked = fuse([one, both])

        assert ranked[0] is both
        assert both.rrf_score > one.rrf_score

    def test_a_chunk_found_by_only_one_arm_still_ranks(self) -> None:
        """Exact-token matches often appear in the keyword arm alone."""
        keyword_only = hit("Madde 7.3", keyword=1)
        ranked = fuse([keyword_only])

        assert ranked[0].rrf_score == pytest.approx(1 / (RRF_K + 1))

    def test_scores_follow_the_published_formula(self) -> None:
        chunk = hit("both", vector=2, keyword=5)
        fuse([chunk])

        assert chunk.rrf_score == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 5))

    def test_ordering_is_deterministic_across_runs(self) -> None:
        """A retrieval metric over a non-deterministic ordering is noise."""
        chunks = [hit(f"c{i}", page=i, vector=1) for i in range(5)]
        first = [c.content for c in fuse(list(chunks))]
        second = [c.content for c in fuse(list(reversed(chunks)))]

        assert first == second

    def test_limit_truncates_after_ranking_not_before(self) -> None:
        chunks = [hit("weak", vector=9), hit("strong", vector=1, keyword=1)]
        ranked = fuse(chunks, limit=1)

        assert len(ranked) == 1
        assert ranked[0].content == "strong"

    def test_two_separate_lists_merge_on_identity(self) -> None:
        shared = hit("shared")
        vector_arm = [shared, hit("vector-only")]
        keyword_arm = [shared, hit("keyword-only")]

        ranked = reciprocal_rank_fusion(vector_arm, keyword_arm)

        assert len(ranked) == 3  # the shared chunk is not duplicated
        merged = next(c for c in ranked if c.content == "shared")
        assert merged.vector_rank == 1
        assert merged.keyword_rank == 1
        assert ranked[0] is merged

    def test_fusing_nothing_returns_nothing(self) -> None:
        assert fuse([]) == []
        assert reciprocal_rank_fusion([], []) == []


# -----------------------------------------------------------------------------
# the retrieval pipeline
# -----------------------------------------------------------------------------


async def test_the_question_is_embedded_with_the_query_path() -> None:
    """Document and query embeddings are asymmetric.

    Swapping them raises nothing and quietly costs recall, so it needs a test
    rather than a comment.
    """
    embedder = StubEmbedder()
    retriever = HybridRetriever(StubStore([hit("a", vector=1)]), embedder)

    await retriever.retrieve(question="Sel kapsanıyor mu?", document_id=DOC, user_id=USER)

    assert embedder.query_calls == ["Sel kapsanıyor mu?"]
    assert embedder.document_calls == []


async def test_both_the_text_and_the_vector_reach_the_store() -> None:
    """Hybrid means hybrid: dropping either arm's input is a silent downgrade."""
    store = StubStore([hit("a", vector=1)])
    await HybridRetriever(store, StubEmbedder()).retrieve(
        question="Madde 7.3 nedir?", document_id=DOC, user_id=USER
    )

    assert store.queries == ["Madde 7.3 nedir?"]
    assert len(store.embeddings[0]) == 1536


async def test_the_accessor_is_passed_through_for_the_access_check() -> None:
    store = StubStore([])
    await HybridRetriever(store, StubEmbedder()).retrieve(
        question="…", document_id=DOC, user_id=None
    )

    assert store.accessors == [None]  # anonymous visitors may still reach samples


async def test_results_are_fused_and_assembled_into_context() -> None:
    store = StubStore([hit("weak", vector=8), hit("strong", vector=1, keyword=1)])

    result = await HybridRetriever(store, StubEmbedder()).retrieve(
        question="…", document_id=DOC, user_id=USER
    )

    assert result.candidates[0].content == "strong"
    assert "[C1]" in result.context.text
    assert result.context.chunks[0].content == "strong"


async def test_an_empty_document_yields_an_empty_context() -> None:
    result = await HybridRetriever(StubStore([]), StubEmbedder()).retrieve(
        question="…", document_id=DOC, user_id=USER
    )

    assert result.context.is_empty


# -----------------------------------------------------------------------------
# query rewriting
# -----------------------------------------------------------------------------


HISTORY = [
    Turn(role="user", content="Deprem hasarı kapsanıyor mu?"),
    Turn(role="assistant", content="Evet, 1.800.000 TL limitle."),
]


async def test_a_follow_up_is_rewritten_into_a_standalone_query() -> None:
    """'peki ya sel?' embedded as written retrieves nothing useful."""
    store = StubStore([hit("a", vector=1)])
    rewriter = ScriptedLLM("Sel hasarı kapsanıyor mu?")

    result = await HybridRetriever(store, StubEmbedder(), rewriter=rewriter).retrieve(
        question="peki ya sel?", document_id=DOC, user_id=USER, history=HISTORY
    )

    assert result.rewritten is True
    assert result.search_query == "Sel hasarı kapsanıyor mu?"
    assert store.queries == ["Sel hasarı kapsanıyor mu?"]
    assert [u.operation for u in result.usage] == ["rewrite"]


async def test_the_first_turn_is_never_rewritten() -> None:
    """With no history there is nothing to resolve, and a call would be waste."""
    rewriter = ScriptedLLM("something else entirely")

    result = await HybridRetriever(StubStore([]), StubEmbedder(), rewriter=rewriter).retrieve(
        question="Sel kapsanıyor mu?", document_id=DOC, user_id=USER, history=[]
    )

    assert rewriter.call_count == 0
    assert result.search_query == "Sel kapsanıyor mu?"


async def test_a_rewriter_outage_falls_back_to_the_question_as_typed() -> None:
    store = StubStore([])

    result = await HybridRetriever(store, StubEmbedder(), rewriter=FailingLLM()).retrieve(
        question="peki ya sel?", document_id=DOC, user_id=USER, history=HISTORY
    )

    assert result.rewritten is False
    assert store.queries == ["peki ya sel?"]


async def test_an_empty_rewrite_is_rejected() -> None:
    store = StubStore([])

    result = await HybridRetriever(store, StubEmbedder(), rewriter=ScriptedLLM("   ")).retrieve(
        question="peki ya sel?", document_id=DOC, user_id=USER, history=HISTORY
    )

    assert result.search_query == "peki ya sel?"
    assert result.rewritten is False
    assert result.usage  # the call still happened and is still billed


async def test_a_runaway_rewrite_is_rejected() -> None:
    """A rewrite that balloons has misunderstood the task.

    A bad rewrite is worse than none: it steers retrieval at a passage the user
    never asked about, and does so invisibly.
    """
    runaway = ScriptedLLM("bir " * 400)

    result = await HybridRetriever(StubStore([]), StubEmbedder(), rewriter=runaway).retrieve(
        question="peki ya sel?", document_id=DOC, user_id=USER, history=HISTORY
    )

    assert result.search_query == "peki ya sel?"
    assert result.rewritten is False


async def test_rewriting_can_be_switched_off_for_ablation() -> None:
    rewriter = ScriptedLLM("rewritten")

    result = await HybridRetriever(
        StubStore([]), StubEmbedder(), rewriter=rewriter, enable_rewrite=False
    ).retrieve(question="peki ya sel?", document_id=DOC, user_id=USER, history=HISTORY)

    assert rewriter.call_count == 0
    assert result.search_query == "peki ya sel?"


# -----------------------------------------------------------------------------
# pgvector serialisation
# -----------------------------------------------------------------------------


class TestPgVector:
    def test_format_is_exact(self) -> None:
        assert to_pgvector([1.0, 2.5] + [0.0] * 1534).startswith("[1.0,2.5,0.0")

    def test_a_wrong_width_vector_is_refused_before_it_reaches_postgres(self) -> None:
        """The error is much clearer here than as an opaque Postgres cast failure."""
        with pytest.raises(ValueError, match="1536"):
            to_pgvector([0.1, 0.2, 0.3])
