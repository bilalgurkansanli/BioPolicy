"""Run the golden dataset and write `eval/report.md`.

    python -m eval.run_eval                       # all four arms
    python -m eval.run_eval --limit 5             # smoke test
    python -m eval.run_eval --arm strict_guarded  # one arm
    python -m eval.run_eval --arm rerender        # rebuild the report, free

This costs money. It is not part of CI.

## The ablation is the point

The run is a 2x2: the **prompt** (strict grounding versus naive) crossed with
the **mechanisms** (citation binding and self-verification, on or off).

An earlier version varied only the mechanisms and found no difference — a true
result, and an uninformative one, because the strict prompt sat underneath both
arms doing the work. Varying both separates the levers: naive_only is the
baseline a normal RAG build reaches, naive_guarded asks whether the mechanisms
rescue a weak prompt, and strict_only asks how much of the product is prompt
alone.

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
from api.generation import prompts
from api.generation.answerer import Answerer
from api.generation.entailment import EntailmentChecker
from api.generation.llm import FailoverLLM, LLMProvider
from api.generation.providers import AnthropicLLM, GeminiLLM
from api.generation.schemas import (
    ANSWER_JSON_SCHEMA,
    ENTAILMENT_JSON_SCHEMA,
    VERIFICATION_JSON_SCHEMA,
    GroundedAnswer,
)
from api.generation.verifier import Verifier
from api.pricing import UnpricedModelError, estimate_cost
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import ChunkStore
from eval import history
from eval.copy import LANGS, Lang
from eval.dataset import GoldenQuestion, load, stats
from eval.metrics import QuestionResult, Report, build_report, locate_evidence
from eval.report import render_report

# Bounded rather than unbounded. Sixty concurrent questions is the reliable way
# to hit a per-minute rate limit and turn a paid run into a wasted one; four
# keeps the whole dataset inside a couple of minutes.
CONCURRENCY = 4

# Prompt (strict / naive) by mechanisms (none / binding+verification / plus the
# entailment check).
#
# The first four arms answered "which lever does the work?" and the answer was
# the prompt: binding and verification changed no decisions while adding ~55% to
# the cost. The report also diagnosed why — neither examines the *inferential*
# step — and the two `_entailed` arms are that diagnosis turned into an
# experiment.
#
# The load-bearing comparison is `naive_only` → `naive_entailed`, not the strict
# pair. The failures the entailment check was built for exist in the naive arm;
# the strict prompt already avoids most of them, so measuring there would ask
# whether a mechanism can fix something that is not broken.
#
#   naive_only      what a normal RAG build does. The baseline.
#   naive_guarded   do binding and verification rescue a naive prompt?  (no)
#   naive_entailed  does checking the inference rescue it?              (the question)
#   strict_only     how much of the product is prompt alone?
#   strict_guarded  the previously shipped configuration.
#   strict_entailed the same, with the fourth mechanism.
ARMS: dict[str, tuple[str, str, bool, bool, bool]] = {
    # key:            (label,                          prompt,        bind,  verify, entail)
    "naive_only": ("naive prompt, no mechanisms", prompts.ANSWER_NAIVE, False, False, False),
    "naive_guarded": ("naive prompt + mechanisms", prompts.ANSWER_NAIVE, True, True, False),
    "naive_entailed": (
        "naive prompt + mechanisms + entailment",
        prompts.ANSWER_NAIVE,
        True,
        True,
        True,
    ),
    "strict_only": ("strict prompt, no mechanisms", prompts.ANSWER, False, False, False),
    "strict_guarded": ("strict prompt + mechanisms", prompts.ANSWER, True, True, False),
    "strict_entailed": (
        "strict prompt + mechanisms + entailment",
        prompts.ANSWER,
        True,
        True,
        True,
    ),
}

REPORT_PATH = Path(__file__).parent / "report.md"


def translated_path(report_path: Path, lang: Lang) -> Path:
    """`report.md` -> `report.tr.md`, beside the original rather than under it.

    The web build reads both by name, and a sibling is one read away from a
    path it already has.
    """
    return report_path.with_suffix(f".{lang}.md")


RESULTS_DIR = Path(__file__).parent / "results"

# Two question sets, two report files, two result directories.
#
# They are kept apart rather than merged because merging would move every number
# in the original table for a reason that has nothing to do with the thing being
# measured — a harder corpus is not a worse system, and a single denominator
# cannot say which it is looking at.
QUESTION_SETS: dict[str, tuple[Path, Path, Path]] = {
    # name:    (questions,                          report,                        results)
    "demo": (
        Path(__file__).parent / "golden" / "questions.json",
        REPORT_PATH,
        RESULTS_DIR,
    ),
    "hard": (
        Path(__file__).parent / "golden" / "questions_hard.json",
        Path(__file__).parent / "report_hard.md",
        RESULTS_DIR / "hard",
    ),
    "injection": (
        Path(__file__).parent / "golden" / "questions_injection.json",
        Path(__file__).parent / "report_injection.md",
        RESULTS_DIR / "injection",
    ),
}

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
            served_text=_served_text(answer),
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


def _served_text(answer: GroundedAnswer) -> str:
    """Everything the user sees, as one lowercased haystack.

    The citation quotes are included because they are displayed beside the
    answer, so an attack payload that survives only inside a quote has still
    reached the reader. Dropped citations are not: they were never shown.
    """
    parts = [answer.answer, *(c.quote for c in answer.citations)]
    return "\n".join(parts).lower()


async def run_arm(
    questions: list[GoldenQuestion],
    *,
    label: str,
    prompt_name: str,
    binding: bool,
    verify: bool,
    entail: bool,
    document_ids: dict[str, tuple[UUID, UUID]],
    retriever: HybridRetriever,
    results_dir: Path = RESULTS_DIR,
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
        entailment=EntailmentChecker(
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=ENTAILMENT_JSON_SCHEMA,
            )
        ),
        enable_citation_binding=binding,
        enable_verification=verify,
        enable_entailment_check=entail,
        prompt_name=prompt_name,
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

    _dump(results, label=label, results_dir=results_dir)
    return build_report(results)


def _dump(results: list[QuestionResult], *, label: str, results_dir: Path = RESULTS_DIR) -> None:
    """Persist per-question results so the report can be re-rendered for free.

    Re-running costs money; changing a heading should not.
    """
    path = results_dir / f"{label.replace(' ', '_')}.json"
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
                    # Only for the injection set, and only because a safety
                    # verdict nobody can re-read is not a verdict. `served_text`
                    # is what the user saw; the two lists say exactly which
                    # substring produced the judgement above it.
                    **(
                        {
                            "attack": r.question.attack,
                            "attack_succeeded": r.attack_succeeded,
                            "forbidden_hits": list(r.forbidden_hits),
                            "required_misses": list(r.required_misses),
                            "served_text": r.served_text,
                        }
                        if r.question.is_attack
                        else {}
                    ),
                }
                for r in results
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_arm(
    label: str,
    *,
    results_dir: Path = RESULTS_DIR,
    questions_path: Path | None = None,
) -> list[QuestionResult] | None:
    """Rebuild an arm's results from disk, so re-rendering costs nothing.

    Re-running the dataset costs real money; changing a heading, adding a
    breakdown, or fixing a caveat should not. The saved rows carry the derived
    fields directly (`retrieval_hit`, `first_hit_rank`) rather than the evidence
    spans, so a later edit to the golden set cannot silently rewrite a past
    run's numbers.
    """
    path = results_dir / f"{label.replace(' ', '_')}.json"
    if not path.exists():
        return None

    by_id = {q.id: q for q in (load(questions_path) if questions_path else load())}
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
                served_text=row.get("served_text", ""),
                latency_ms=row["latency_ms"],
                cost_usd=row["cost_usd"],
                error=row["error"],
            )
        )
    return results


async def run(*, limit: int | None, arm: str, question_set: str) -> int:
    settings = get_settings()
    questions_path, report_path, results_dir = QUESTION_SETS[question_set]
    questions = load(questions_path)
    if limit:
        questions = questions[:limit]

    summary = stats(questions)
    print(f"{summary.total} questions · {summary.negative_share:.0%} negatives")
    print(f"model: {settings.anthropic_model}")

    pool = await create_pool()
    try:
        document_ids: dict[str, tuple[UUID, UUID]] = {}
        for row in await pool.fetch(
            "select id, user_id, filename from documents where status = 'ready'"
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
        selected = list(ARMS) if arm in ("all", "rerender") else [arm]

        for key in selected:
            label, prompt_name, binding, verify, entail = ARMS[key]
            if arm == "rerender":
                saved = load_arm(label, results_dir=results_dir, questions_path=questions_path)
                if saved:
                    arms[key] = build_report(saved)
                    print(f"  loaded {len(saved)} saved results for {label}")
                continue
            arms[key] = await run_arm(
                questions,
                label=label,
                prompt_name=prompt_name,
                binding=binding,
                verify=verify,
                entail=entail,
                document_ids=document_ids,
                retriever=retriever,
                results_dir=results_dir,
            )

        if not arms:
            print(f"{R}No results. Run the eval first.{RESET}")
            return 1

        # Corpus shape, so the report can judge whether recall was measurable at
        # all rather than reporting a number that only reflects document size.
        chunks_per_document = {
            str(row["filename"]).removesuffix(".pdf"): int(row["n"])
            for row in await pool.fetch(
                "select d.filename, count(c.id) as n from documents d "
                "join chunks c on c.document_id = d.id "
                "group by d.filename"
            )
        }

        commit = git_commit()
        generated_at = datetime.now(UTC)

        # One run, one set of numbers, two languages. Rendered together from the
        # same `arms` so the pair cannot disagree: a Turkish report produced by a
        # separate command would eventually be a report of a different run.
        renders = {
            lang: render_report(
                arms,
                model=settings.anthropic_model,
                embedding_model=settings.gemini_embedding_model,
                commit=commit,
                generated_at=generated_at,
                dataset=summary,
                chunks_per_document=chunks_per_document,
                context_chunk_count=CONTEXT_CHUNK_COUNT,
                lang=lang,
            )
            for lang in LANGS
        }
        if arm != "rerender":
            # Only arms that actually ran. A rerender rebuilds prose from saved
            # results and appending for it would record a run that never
            # happened — which is exactly the kind of number this file exists to
            # make impossible.
            history.append(
                [
                    history.row_from(
                        report,
                        commit=commit,
                        question_set=question_set,
                        arm=key,
                        model=settings.anthropic_model,
                        # Per arm, not per run: the naive arms deliberately use a
                        # different prompt, and recording one version for all of
                        # them would misattribute their numbers.
                        prompt=ARMS[key][1],
                    )
                    for key, report in arms.items()
                ]
            )

        for lang, markdown in renders.items():
            path = report_path if lang == "en" else translated_path(report_path, lang)
            path.write_text(markdown, encoding="utf-8")
            print(f"\n{G}Wrote {path}{RESET}")

        primary = arms.get("strict_guarded") or next(iter(arms.values()))
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
        choices=[*ARMS, "all", "rerender"],
        default="all",
        help="Which arm(s) to run. `rerender` rebuilds the report from saved results, free.",
    )
    parser.add_argument(
        "--set",
        choices=tuple(QUESTION_SETS),
        default="demo",
        help=(
            "demo: the 70-question set over the three bundled documents (default). "
            "hard: the adversarial set — a self-contradicting policy and a "
            "two-column layout — reported separately so the demo numbers stay "
            "comparable across arms. "
            "injection: a policy that tries to give the system orders, scored on "
            "whether any of them were carried out."
        ),
    )
    args = parser.parse_args()
    return asyncio.run(run(limit=args.limit, arm=args.arm, question_set=args.set))


if __name__ == "__main__":
    sys.exit(main())
