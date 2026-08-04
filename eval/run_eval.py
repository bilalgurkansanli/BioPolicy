"""Run the golden dataset and write `eval/report.md`.

    python -m eval.run_eval                  # full run, both ablation arms
    python -m eval.run_eval --limit 5        # smoke test on five questions
    python -m eval.run_eval --arm on         # only the mechanisms-on arm

This costs money. It is not part of CI.

## The ablation is the point

Each question runs twice: once with citation binding and self-verification
enabled, once with both disabled. The second arm is what the product would be
without the layer this project exists to build, and publishing the pair is the
difference between a claim and a measurement. A single column of good numbers
proves nothing — the reader cannot tell whether the mechanisms did anything or
whether the model was simply well-behaved.

## Reproducibility

Every run records the model id, the prompt version, the dataset size and the git
commit into the report. A metric without those attached cannot be compared
against a later run, and comparing across runs is the only reason to keep the
numbers at all.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from api.config import get_settings
from api.constants import CONTEXT_CHUNK_COUNT
from api.db import create_pool
from api.generation.answerer import Answerer
from api.generation.llm import FailoverLLM, LLMProvider
from api.generation.providers import AnthropicLLM, GeminiLLM
from api.generation.schemas import ANSWER_JSON_SCHEMA, VERIFICATION_JSON_SCHEMA
from api.generation.verifier import Verifier
from api.pricing import UnpricedModelError, estimate_cost
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import ChunkStore
from eval.dataset import GoldenQuestion, load, stats
from eval.metrics import QuestionResult, Report, build_report, locate_evidence
from eval.report import render_report

# Bounded rather than unbounded. Sixty concurrent questions is the reliable way
# to hit a per-minute rate limit and turn a paid run into a wasted one; four
# keeps the whole dataset inside a couple of minutes.
CONCURRENCY = 4

REPORT_PATH = Path(__file__).parent / "report.md"
RESULTS_DIR = Path(__file__).parent / "results"

G, R, Y, D, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def build_answering_llm(*, schema: dict[str, object]) -> LLMProvider:
    settings = get_settings()
    providers: list[LLMProvider] = [
        AnthropicLLM(settings.anthropic_api_key or "", settings.anthropic_model, json_schema=schema)
    ]
    if settings.google_api_key and settings.gemini_fallback_model:
        providers.append(
            GeminiLLM(settings.google_api_key, settings.gemini_fallback_model, json_schema=schema)
        )
    return FailoverLLM(providers=providers)


async def run_one(
    question: GoldenQuestion,
    *,
    document_ids: dict[str, tuple[UUID, UUID]],
    retriever: HybridRetriever,
    answerer: Answerer,
) -> QuestionResult:
    started = time.monotonic()
    document_id, user_id = document_ids[question.document]

    try:
        retrieved = await retriever.retrieve(
            question=question.question, document_id=document_id, user_id=user_id
        )
        # Evidence is looked for in the chunks that actually reached the prompt,
        # not in everything retrieved. A span sitting in a chunk that was
        # trimmed for budget was not available to the model, and counting it as
        # a retrieval hit would flatter the number.
        texts = [c.content for c in retrieved.context.chunks]
        found, first_rank = locate_evidence(question, texts)

        outcome = await answerer.answer(
            question=question.question,
            context=retrieved.context,
            language=question.lang,
        )
        answer = outcome.answer

        cost = 0.0
        for usage in outcome.usage:
            try:
                cost += estimate_cost(
                    usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
            except UnpricedModelError:
                pass

        return QuestionResult(
            question=question,
            answer_found=not answer.refused,
            suppressed=answer.suppressed,
            suppression_reason=answer.suppression_reason,
            evidence_found=found,
            first_hit_rank=first_rank,
            retrieved_count=len(retrieved.context.chunks),
            citations_offered=len(answer.citations) + len(answer.dropped_citations),
            citations_kept=len(answer.citations),
            groundedness=answer.groundedness,
            latency_ms=(time.monotonic() - started) * 1000,
            cost_usd=cost,
        )
    except Exception as exc:
        return QuestionResult(
            question=question,
            answer_found=False,
            latency_ms=(time.monotonic() - started) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_arm(
    questions: list[GoldenQuestion],
    *,
    label: str,
    binding: bool,
    verify: bool,
    document_ids: dict[str, tuple[UUID, UUID]],
    retriever: HybridRetriever,
) -> Report:
    settings = get_settings()
    verifier = Verifier(
        AnthropicLLM(
            settings.anthropic_api_key or "",
            settings.anthropic_model,
            json_schema=VERIFICATION_JSON_SCHEMA,
        )
    )
    answerer = Answerer(
        build_answering_llm(schema=ANSWER_JSON_SCHEMA),
        verifier=verifier,
        enable_citation_binding=binding,
        enable_verification=verify,
    )

    semaphore = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def guarded(question: GoldenQuestion) -> QuestionResult:
        nonlocal done
        async with semaphore:
            result = await run_one(
                question,
                document_ids=document_ids,
                retriever=retriever,
                answerer=answerer,
            )
        done += 1
        mark = (
            f"{R}E{RESET}"
            if result.error
            else (f"{G}·{RESET}" if result.decision_correct else f"{Y}x{RESET}")
        )
        print(mark, end="", flush=True)
        if done % 40 == 0:
            print(f"  {done}/{len(questions)}")
        return result

    print(f"\n[{label}]  binding={binding}  verification={verify}")
    started = time.monotonic()
    results = list(await asyncio.gather(*(guarded(q) for q in questions)))
    print(f"\n  {len(results)} questions in {time.monotonic() - started:.0f}s")

    # Name every disagreement. An aggregate that hides which questions went
    # wrong cannot be acted on — and the individual failures are usually more
    # informative than the percentage they roll up into.
    wrong = [r for r in results if not r.decision_correct or r.error]
    for result in wrong:
        expected = "answerable" if result.question.expected_answer_found else "unanswerable"
        got = "answered" if result.answer_found else "refused"
        detail = result.error or f"expected {expected}, {got}"
        print(f"    {Y}{result.question.id}{RESET}  {detail}")
        print(f"      {D}{result.question.question[:78]}{RESET}")

    _dump(results, label=label)
    return build_report(results)


def _dump(results: list[QuestionResult], *, label: str) -> None:
    """Persist per-question results so the report can be re-rendered for free.

    Re-running costs money; changing a heading should not.
    """
    path = RESULTS_DIR / f"{label.replace(' ', '_')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "id": r.question.id,
                    "category": r.question.category,
                    "lang": r.question.lang,
                    "expected_answer_found": r.question.expected_answer_found,
                    "answer_found": r.answer_found,
                    "decision_correct": r.decision_correct,
                    "retrieval_hit": r.retrieval_hit,
                    "first_hit_rank": r.first_hit_rank,
                    "citations_offered": r.citations_offered,
                    "citations_kept": r.citations_kept,
                    "suppressed": r.suppressed,
                    "groundedness": r.groundedness,
                    "latency_ms": round(r.latency_ms),
                    "cost_usd": round(r.cost_usd, 6),
                    "error": r.error,
                }
                for r in results
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_arm(label: str) -> list[QuestionResult] | None:
    """Rebuild an arm's results from disk, so re-rendering costs nothing.

    Re-running the dataset costs real money; changing a heading, adding a
    breakdown, or fixing a caveat should not. The saved rows carry the derived
    fields directly (`retrieval_hit`, `first_hit_rank`) rather than the evidence
    spans, so a later edit to the golden set cannot silently rewrite a past
    run's numbers.
    """
    path = RESULTS_DIR / f"{label.replace(' ', '_')}.json"
    if not path.exists():
        return None

    by_id = {q.id: q for q in load()}
    results: list[QuestionResult] = []
    for row in json.loads(path.read_text(encoding="utf-8")):
        question = by_id.get(row["id"])
        if question is None:
            continue
        results.append(
            QuestionResult(
                question=question,
                answer_found=row["answer_found"],
                suppressed=row["suppressed"],
                # Evidence is reconstructed as "all of it" or "none", which
                # reproduces the recorded retrieval_hit exactly without
                # depending on the current golden set.
                evidence_found=question.expected_evidence if row["retrieval_hit"] else (),
                first_hit_rank=row["first_hit_rank"],
                citations_offered=row["citations_offered"],
                citations_kept=row["citations_kept"],
                groundedness=row["groundedness"],
                latency_ms=row["latency_ms"],
                cost_usd=row["cost_usd"],
                error=row["error"],
            )
        )
    return results


async def run(*, limit: int | None, arm: str) -> int:
    settings = get_settings()
    questions = load()
    if limit:
        questions = questions[:limit]

    summary = stats(questions)
    print(f"{summary.total} questions · {summary.negative_share:.0%} negatives")
    print(f"model: {settings.anthropic_model}")

    pool = await create_pool()
    try:
        document_ids: dict[str, tuple[UUID, UUID]] = {}
        for row in await pool.fetch(
            "select id, user_id, filename from documents where is_sample and status = 'ready'"
        ):
            slug = str(row["filename"]).removesuffix(".pdf")
            document_ids[slug] = (UUID(str(row["id"])), UUID(str(row["user_id"])))

        missing = {q.document for q in questions} - set(document_ids)
        if missing:
            print(f"{R}Not ingested: {', '.join(sorted(missing))}{RESET}")
            print("Run: python -m api.scripts.seed_samples")
            return 1

        retriever = HybridRetriever(
            ChunkStore(pool),
            GeminiEmbedder(settings.google_api_key or "", settings.gemini_embedding_model),
        )

        arms: dict[str, Report] = {}
        if arm == "rerender":
            for key, label in (("on", "mechanisms ON"), ("off", "mechanisms OFF")):
                saved = load_arm(label)
                if saved:
                    arms[key] = build_report(saved)
                    print(f"  loaded {len(saved)} saved results for {label}")
            if not arms:
                print(f"{R}No saved results in {RESULTS_DIR}. Run the eval first.{RESET}")
                return 1
        if arm in ("on", "both"):
            arms["on"] = await run_arm(
                questions,
                label="mechanisms ON",
                binding=True,
                verify=True,
                document_ids=document_ids,
                retriever=retriever,
            )
        if arm in ("off", "both"):
            arms["off"] = await run_arm(
                questions,
                label="mechanisms OFF",
                binding=False,
                verify=False,
                document_ids=document_ids,
                retriever=retriever,
            )

        # Corpus shape, so the report can judge whether recall was measurable at
        # all rather than reporting a number that only reflects document size.
        chunks_per_document = {
            str(row["filename"]).removesuffix(".pdf"): int(row["n"])
            for row in await pool.fetch(
                "select d.filename, count(c.id) as n from documents d "
                "join chunks c on c.document_id = d.id where d.is_sample "
                "group by d.filename"
            )
        }

        markdown = render_report(
            arms,
            model=settings.anthropic_model,
            embedding_model=settings.gemini_embedding_model,
            commit=git_commit(),
            generated_at=datetime.now(UTC),
            dataset=summary,
            chunks_per_document=chunks_per_document,
            context_chunk_count=CONTEXT_CHUNK_COUNT,
        )
        REPORT_PATH.write_text(markdown, encoding="utf-8")
        print(f"\n{G}Wrote {REPORT_PATH}{RESET}")

        primary = arms.get("on") or next(iter(arms.values()))
        print(f"\n  recall@8            {primary.retrieval.recall_at_k:.0%}")
        print(f"  refusal accuracy    {primary.refusal.refusal_accuracy:.0%}")
        print(f"  false-refusal rate  {primary.refusal.false_refusal_rate:.0%}")
        print(f"  balanced            {primary.refusal.balanced_accuracy:.0%}")
        print(f"  citation validity   {primary.citations.validity:.0%}")
        print(f"  total cost          ${sum(a.cost.total_usd for a in arms.values()):.2f}")
        return 0
    finally:
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Run only the first N questions.")
    parser.add_argument(
        "--arm",
        choices=["on", "off", "both", "rerender"],
        default="both",
        help="Which arms to run. `rerender` rebuilds the report from saved results, free.",
    )
    args = parser.parse_args()
    return asyncio.run(run(limit=args.limit, arm=args.arm))


if __name__ == "__main__":
    sys.exit(main())
