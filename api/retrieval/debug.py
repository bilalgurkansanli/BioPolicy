"""Retrieval inspection CLI.

    python -m api.retrieval.debug "Sel hasarı kapsanıyor mu?"
    python -m api.retrieval.debug --doc commercial "what is the BI limit?" --show-context

Prints the ranked chunks with their per-arm ranks and RRF scores, so you can see
*why* something ranked where it did rather than only that it did.

Runs entirely offline against the bundled sample PDFs, with no database and no
API key. The trade-off is stated at the top of every run and is worth repeating
here: the offline store has no embeddings, so it cannot find `su baskını` from
`sel`. It answers "did the pipeline carry the right text through", not "is
retrieval any good". The second question is Phase 5's, with real embeddings and
published numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from api.ingest.chunker import Chunker
from api.ingest.parsers import PdfParser
from api.retrieval.hybrid import HybridRetriever
from api.retrieval.local import InMemoryStore, NullEmbedder

SAMPLES = Path(__file__).resolve().parents[2] / "eval" / "golden" / "samples"

ALIASES = {
    "konut": "konut-sigortasi-tr",
    "commercial": "commercial-property-liability-en",
    "saglik": "tamamlayici-saglik-tr-scanned",
}

BANNER = (
    "offline mode — lexical scoring only, no embeddings.\n"
    "  This shows what the pipeline carried through, NOT retrieval quality:\n"
    "  it cannot match 'su baskını' to 'sel'. See Phase 5 for measured numbers.\n"
)


async def run(document: str, question: str, *, top: int, show_context: bool) -> int:
    slug = ALIASES.get(document, document)
    path = SAMPLES / f"{slug}.pdf"
    if not path.exists():
        print(f"No such sample: {slug}", file=sys.stderr)
        print(f"Available: {', '.join(sorted(ALIASES))}", file=sys.stderr)
        return 2

    parsed = await PdfParser().parse(path.read_bytes())
    chunks = Chunker().chunk(parsed)
    if not chunks:
        print(f"{slug} produced no chunks — it is probably a scan; OCR is required.")
        return 1

    store = InMemoryStore.from_chunks(chunks)
    retriever = HybridRetriever(store, NullEmbedder())
    result = await retriever.retrieve(
        question=question, document_id=uuid4(), user_id=None, max_chunks=top
    )

    print(f"\n{BANNER}")
    print(f"document : {slug}  ({parsed.page_count} pages, {len(chunks)} chunks)")
    print(f"question : {question}")
    print(f"searched : {result.search_query}")
    print(
        f"retrieved: {len(result.candidates)} candidates, {len(result.context.chunks)} in context"
    )
    print("=" * 78)

    if not result.candidates:
        print(
            "\nNothing matched. With a real vector arm this would often still return\n"
            "something semantically related — that is the gap this mode cannot show."
        )
        return 0

    for chunk in result.candidates[:top]:
        arms = []
        if chunk.vector_rank is not None:
            arms.append(f"v#{chunk.vector_rank}")
        if chunk.keyword_rank is not None:
            arms.append(f"k#{chunk.keyword_rank}")

        header = (
            f"[{chunk.context_id or '  -'}] rrf={chunk.rrf_score:.5f} "
            f"({', '.join(arms) or 'no arm'})  p{chunk.page_start}"
        )
        print(f"\n{header}")
        print(f"      {chunk.section_path or '(no section)'}")
        body = chunk.content if len(chunk.content) < 400 else chunk.content[:397] + "..."
        for line in body.splitlines():
            print(f"      {line}")

    if show_context:
        print("\n" + "=" * 78)
        print(f"ASSEMBLED CONTEXT ({result.context.token_count} tokens)")
        print("=" * 78)
        print(result.context.text)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="The question to search for.")
    parser.add_argument(
        "--doc",
        default="konut",
        help=f"Sample document. One of: {', '.join(sorted(ALIASES))}. Default: konut.",
    )
    parser.add_argument("--top", type=int, default=5, help="How many results to print.")
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Also print the assembled prompt context verbatim.",
    )
    args = parser.parse_args()

    return asyncio.run(run(args.doc, args.question, top=args.top, show_context=args.show_context))


if __name__ == "__main__":
    raise SystemExit(main())
