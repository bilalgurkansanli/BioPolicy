"""Ask a question end to end, against live data and live models.

    python -m api.scripts.ask "Deprem teminatının limiti nedir?"
    python -m api.scripts.ask --doc saglik "Doğum masrafları karşılanır mı?"
    python -m api.scripts.ask --no-verify "..."      # ablation: verification off
    python -m api.scripts.ask --no-binding "..."     # ablation: binding off

Unlike `api.retrieval.debug`, which runs offline on lexical scoring, this uses
the real embedder, the real database and the real model. It prints every stage
so the anti-hallucination layer is inspectable rather than a black box: what was
retrieved, what the model claimed, which citations survived binding, what the
verifier made of the draft, and what it cost.

The two ablation flags are the same switches the evaluation harness flips. They
are here so a specific answer can be examined with and without a mechanism,
which is a faster way to understand what each one does than reading the numbers
in aggregate.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from uuid import UUID

from api.config import get_settings
from api.db import create_pool
from api.generation.answerer import Answerer
from api.generation.llm import FailoverLLM
from api.generation.providers import AnthropicLLM, GeminiLLM
from api.generation.schemas import ANSWER_JSON_SCHEMA, VERIFICATION_JSON_SCHEMA
from api.generation.verifier import Verifier
from api.pricing import UnpricedModelError, estimate_cost
from api.retrieval.gemini_embedder import GeminiEmbedder
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.store import ChunkStore

ALIASES = {
    "konut": "konut-sigortasi-tr.pdf",
    "commercial": "commercial-property-liability-en.pdf",
    "saglik": "tamamlayici-saglik-tr-scanned.pdf",
}

G, R, Y, C, D, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[36m",
    "\033[2m",
    "\033[0m",
)


def _use_utf8() -> None:
    """Stop a Turkish Windows console from killing the run on a box-drawing dash.

    `python -m api.scripts.ask` died with a UnicodeEncodeError before printing
    anything: the default console encoding here is cp1254, which has no `─`, and
    the failure happens in `print` rather than anywhere near the pipeline being
    debugged. Since this tool exists to inspect Turkish documents, a console
    that cannot encode the output is the environment it is most likely to meet.

    `errors="replace"` on top of UTF-8 because a debugging aid must never be the
    thing that fails: on a console that still cannot represent a character, a
    question mark in the rule is a better outcome than a traceback.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def rule(title: str) -> None:
    print(f"\n{C}{'─' * 4} {title} {'─' * max(0, 66 - len(title))}{RESET}")


async def run(question: str, doc: str, *, verify: bool, binding: bool, language: str) -> int:
    settings = get_settings()
    filename = ALIASES.get(doc, doc)

    pool = await create_pool()
    try:
        row = await pool.fetchrow(
            "select id, user_id, filename, detected_lang from documents "
            "where filename = $1 and status = 'ready'",
            filename,
        )
        if row is None:
            print(f"{R}No ready document named {filename!r}.{RESET}")
            print(f"Available: {', '.join(sorted(ALIASES))}")
            return 2

        # --- retrieval ------------------------------------------------------
        embedder = GeminiEmbedder(settings.google_api_key or "", settings.gemini_embedding_model)
        retriever = HybridRetriever(ChunkStore(pool), embedder)

        started = time.monotonic()
        retrieved = await retriever.retrieve(
            question=question,
            document_id=UUID(str(row["id"])),
            user_id=UUID(str(row["user_id"])),
        )
        retrieval_seconds = time.monotonic() - started

        rule("RETRIEVAL")
        print(f"document : {row['filename']}  (lang={row['detected_lang']})")
        print(
            f"candidates: {len(retrieved.candidates)}  "
            f"in context: {len(retrieved.context.chunks)}  "
            f"tokens: {retrieved.context.token_count}  "
            f"({retrieval_seconds:.1f}s)"
        )
        for chunk in retrieved.context.chunks:
            arms = ",".join(
                filter(
                    None,
                    [
                        f"v#{chunk.vector_rank}" if chunk.vector_rank else "",
                        f"k#{chunk.keyword_rank}" if chunk.keyword_rank else "",
                    ],
                )
            )
            print(f"  [{chunk.context_id}] p{chunk.page_start} {arms:<9} {chunk.section_path[:44]}")

        # --- generation -----------------------------------------------------
        primary = AnthropicLLM(
            settings.anthropic_api_key or "",
            settings.anthropic_model,
            json_schema=ANSWER_JSON_SCHEMA,
        )
        providers: list[object] = [primary]
        if settings.google_api_key and settings.gemini_fallback_model:
            providers.append(
                GeminiLLM(
                    settings.google_api_key,
                    settings.gemini_fallback_model,
                    json_schema=ANSWER_JSON_SCHEMA,
                )
            )
        answering = FailoverLLM(providers=providers)  # type: ignore[arg-type]

        verifier = Verifier(
            AnthropicLLM(
                settings.anthropic_api_key or "",
                settings.anthropic_model,
                json_schema=VERIFICATION_JSON_SCHEMA,
            )
        )

        answerer = Answerer(
            answering,
            verifier=verifier,
            enable_citation_binding=binding,
            enable_verification=verify,
        )

        started = time.monotonic()
        outcome = await answerer.answer(
            question=question, context=retrieved.context, language=language
        )
        answer_seconds = time.monotonic() - started
        answer = outcome.answer

        # --- result ---------------------------------------------------------
        rule("ANSWER")
        if answer.refused:
            label = f"{R}SUPPRESSED{RESET}" if answer.suppressed else f"{Y}REFUSED{RESET}"
            reason = f"  ({answer.suppression_reason})" if answer.suppression_reason else ""
            print(f"{label}{reason}\n")
        else:
            print(f"{G}SERVED{RESET}  confidence={answer.confidence}\n")
        print(answer.answer)

        if answer.caveats:
            print(f"\n{D}caveats:{RESET}")
            for caveat in answer.caveats:
                print(f"  · {caveat}")

        rule("CITATIONS")
        if not answer.citations and not answer.dropped_citations:
            print(f"{D}none offered{RESET}")
        for citation in answer.citations:
            mark = "exact" if citation.exact else f"{Y}fuzzy{RESET}"
            print(f"  {G}KEPT{RESET}    [{citation.context_id}] p{citation.page}  ({mark})")
            print(f'          "{citation.quote[:88]}"')
        for dropped in answer.dropped_citations:
            print(f"  {R}DROPPED{RESET} [{dropped.context_id}]  reason={dropped.reason}")
            print(f'          "{dropped.quote[:88]}"')

        rule("VERIFICATION")
        if answer.groundedness is None:
            print(f"{D}did not run{RESET}" if verify else f"{D}disabled{RESET}")
        else:
            band = (
                f"{G}serve{RESET}"
                if answer.groundedness >= 0.8
                else (f"{Y}warn{RESET}" if answer.groundedness >= 0.5 else f"{R}suppress{RESET}")
            )
            print(f"groundedness = {answer.groundedness:.2f}   band = {band}")

        rule("COST")
        total = 0.0
        for usage in outcome.usage:
            try:
                cost = estimate_cost(
                    usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
                total += cost
                print(
                    f"  {usage.operation:<8} {usage.model:<28} "
                    f"in {usage.input_tokens:>6}  out {usage.output_tokens:>5}  ${cost:.5f}"
                )
            except UnpricedModelError:
                print(
                    f"  {usage.operation:<8} {usage.model:<28} "
                    f"in {usage.input_tokens:>6}  out {usage.output_tokens:>5}  "
                    f"{Y}unpriced{RESET}"
                )
        print(f"\n  total: ${total:.5f}   latency: {answer_seconds:.1f}s")
        if total > 0:
            print(
                f"  {D}${settings.global_budget_usd:.0f} budget ≈ {int(settings.global_budget_usd / total):,} questions{RESET}"
            )
        return 0
    finally:
        await pool.close()


def main() -> int:
    _use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--doc", default="konut", help=f"One of: {', '.join(sorted(ALIASES))}")
    parser.add_argument("--lang", default="tr", help="Reply language: tr or en.")
    parser.add_argument("--no-verify", action="store_true", help="Ablation: skip verification.")
    parser.add_argument(
        "--no-binding", action="store_true", help="Ablation: do not check citations."
    )
    args = parser.parse_args()

    return asyncio.run(
        run(
            args.question,
            args.doc,
            verify=not args.no_verify,
            binding=not args.no_binding,
            language=args.lang,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
