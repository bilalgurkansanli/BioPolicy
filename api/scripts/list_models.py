"""Verify providers and discover model ids. Run this first, before anything else.

    python -m api.scripts.list_models

It does three things, in increasing order of importance:

1. **Lists Gemini models**, filtered by capability, so `GEMINI_FALLBACK_MODEL`
   and `GEMINI_OCR_MODEL` can be filled in from a live list rather than guessed
   (ADR 004).

2. **Confirms the Anthropic model answers**, with one tiny request.

3. **Tests constraint C3 against reality.** This is the one that matters. The
   entire storage design rests on `gemini-embedding-001` honouring
   `output_dimensionality: 1536`. Until this script has run, that is a
   documented assumption and nothing more — a plausible claim in an ADR. This
   makes one real embedding call and measures the vector.

Total cost of a full run is a fraction of a cent.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, cast

from api.config import get_settings
from api.constants import EMBEDDING_DIM

# Capabilities we care about, in the order we want them printed.
INTERESTING = ("generateContent", "embedContent")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}WARN{RESET}  {msg}")


async def check_anthropic(api_key: str, model: str) -> bool:
    print(f"\nAnthropic — {model}")
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
        )
    except Exception as exc:
        fail(f"{type(exc).__name__}: {exc}")
        return False

    text = "".join(b.text for b in message.content if b.type == "text").strip()
    ok(f"responded {text!r}")
    print(
        f"        {DIM}resolved model: {message.model} · "
        f"in {message.usage.input_tokens} tok, out {message.usage.output_tokens} tok{RESET}"
    )
    return True


async def list_gemini_models(api_key: str) -> None:
    print("\nGoogle — available models")
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        models = [m async for m in await client.aio.models.list()]
    except Exception as exc:
        fail(f"could not list models: {type(exc).__name__}: {exc}")
        return

    for capability in INTERESTING:
        matching = [
            m for m in models if capability in (getattr(m, "supported_actions", None) or [])
        ]
        print(f"\n  {capability} ({len(matching)}):")
        for model in sorted(matching, key=lambda m: m.name or ""):
            # The API returns "models/gemini-x"; the id used in requests is the
            # part after the slash.
            model_id = (model.name or "").removeprefix("models/")
            print(f"    {model_id}")

    print(
        f"\n  {DIM}Pick one generateContent model for GEMINI_FALLBACK_MODEL and one "
        f"for GEMINI_OCR_MODEL (it must accept image input).\n"
        f"  Record both in docs/RUNBOOK.md with today's date.{RESET}"
    )


async def verify_embedding_dimensions(api_key: str, model: str) -> bool:
    """The C3 check. This is why the script exists."""
    print(f"\nConstraint C3 — {model} at {EMBEDDING_DIM} dimensions")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = await client.aio.models.embed_content(
            model=model,
            contents=cast(Any, ["Deprem teminatı 1.800.000 TL ile sınırlıdır."]),
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIM,
            ),
        )
    except Exception as exc:
        fail(f"{type(exc).__name__}: {exc}")
        print(
            f"        {DIM}If output_dimensionality is rejected, the storage design "
            f"needs revisiting — see docs/ARCHITECTURE.md constraint C3.{RESET}"
        )
        return False

    embeddings = response.embeddings or []
    if not embeddings:
        fail("no embedding returned")
        return False

    width = len(embeddings[0].values or [])
    if width != EMBEDDING_DIM:
        fail(f"asked for {EMBEDDING_DIM} dimensions, received {width}")
        print(
            f"        {DIM}The vector(1536) column and the HNSW index both assume "
            f"{EMBEDDING_DIM}. Do not ingest anything until this matches.{RESET}"
        )
        return False

    ok(f"received exactly {width} dimensions — under pgvector's 2000 HNSW ceiling")
    return True


async def run(*, skip_list: bool) -> int:
    settings = get_settings()
    failures = 0

    print("=" * 68)
    print("BioPolicy — provider verification")
    print("=" * 68)

    if settings.anthropic_api_key:
        if not await check_anthropic(settings.anthropic_api_key, settings.anthropic_model):
            failures += 1
    else:
        warn("\nANTHROPIC_API_KEY is not set — skipping")
        failures += 1

    if settings.google_api_key:
        if not await verify_embedding_dimensions(
            settings.google_api_key, settings.gemini_embedding_model
        ):
            failures += 1
        if not skip_list:
            await list_gemini_models(settings.google_api_key)
    else:
        warn("\nGOOGLE_API_KEY is not set — skipping")
        failures += 1

    print("\n" + "=" * 68)
    if failures:
        print(f"{RED}{failures} check(s) failed.{RESET} Nothing was ingested.")
    else:
        print(f"{GREEN}All checks passed.{RESET} Safe to run migrations and ingest.")
    print("=" * 68)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-list",
        action="store_true",
        help="Only run the verification checks; do not enumerate Gemini models.",
    )
    args = parser.parse_args()
    return asyncio.run(run(skip_list=args.skip_list))


if __name__ == "__main__":
    sys.exit(main())
