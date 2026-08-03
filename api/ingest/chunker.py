"""Turns a `ParsedDocument` into embeddable, citable chunks.

Three rules govern this module, in priority order.

**1. A table is never split.** In an insurance policy the coverage schedule is
the answer to most of the questions worth asking. A chunk containing
`| Sel ve Su Baskını | 750.000 |` answers "what is the flood limit?". Two chunks,
one holding the perils and one holding the numbers, answer nothing — and worse,
either one retrieved alone looks like relevant context, so the model produces a
confident figure from the wrong row. Splitting a coverage table mid-row is the
single most common way this class of system fails. A table therefore becomes its
own chunk regardless of size, even when that chunk is oversized.

**2. Section context travels into vector space, not onto the screen.** A chunk
reading "…is excluded." is useless in isolation but perfectly clear as
"Madde 4 > 4.7 > …is excluded." The section path is prepended to the *embedded*
text and kept out of the *displayed* text, so retrieval gets the context and the
user gets the clause as written.

**3. Chunk boundaries follow the document's own structure.** Sections do not
bleed into each other; a chunk never spans a heading.

## On token counting

Sizes are measured with a real tokenizer (`cl100k_base` via tiktoken), not a
characters-divided-by-four heuristic. Measured on this project's own fixtures,
Turkish costs roughly **1.9× the tokens of equivalent English** — 32 tokens
against 17 for the same sentence about the same earthquake limit. A character
heuristic would therefore produce Turkish chunks nearly twice the intended size,
blowing the context budget on exactly the documents this product exists to
serve.

Note the tokenizer is OpenAI's, and the answering model is Claude. It is used
here as a *consistent yardstick* for chunk budgeting, which is all this needs.
Cost accounting must use the usage figures the provider actually reports —
never this.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.utils import get_tokenizer

from api.constants import CHUNK_OVERLAP_TOKENS, CHUNK_TARGET_TOKENS
from api.ingest.sentences import split_sentences
from api.ingest.types import BBox, ParsedBlock, ParsedDocument
from api.logging_config import get_logger

log = get_logger(__name__)

_tokenizer = get_tokenizer()


def count_tokens(text: str) -> int:
    return len(_tokenizer(text))


@dataclass(slots=True)
class Chunk:
    """One retrievable unit, ready to embed and to cite."""

    ordinal: int
    content: str
    """What the user sees and what a citation quote is checked against."""

    content_type: str  # 'text' | 'table'
    section_path: str
    page_start: int
    page_end: int
    token_count: int
    bbox: BBox | None = None

    @property
    def embed_text(self) -> str:
        """What actually gets embedded.

        The section path rides along so that a clause reading "…is excluded."
        still carries "Madde 4 > İstisnalar" into vector space. Deliberately not
        part of `content`: the user should see the clause as written, and a
        citation quote must be verifiable against the document's own words.
        """
        return f"{self.section_path}\n\n{self.content}" if self.section_path else self.content


@dataclass(slots=True)
class _Accumulator:
    blocks: list[ParsedBlock] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    tokens: int = 0

    def clear(self) -> None:
        self.blocks.clear()
        self.texts.clear()
        self.tokens = 0

    @property
    def empty(self) -> bool:
        return not self.texts


class Chunker:
    def __init__(
        self,
        target_tokens: int = CHUNK_TARGET_TOKENS,
        overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
    ) -> None:
        if overlap_tokens >= target_tokens:
            raise ValueError("overlap must be smaller than the target chunk size")
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        # WHY llama-index only here: sentence-boundary splitting with a token
        # budget and overlap is fiddly to get right and entirely uninteresting
        # to own. Everything structural above it is hand-written, because that
        # is the part worth understanding. See docs/adr/003 and docs/adr/008.
        self._splitter = SentenceSplitter(
            chunk_size=target_tokens,
            chunk_overlap=overlap_tokens,
            tokenizer=_tokenizer,
            # WHY our own sentence splitter: the default pulls NLTK's punkt,
            # which needs a runtime model download, is trained on English only,
            # and is unimportable under the standard in-project `.venv` layout.
            # See api/ingest/sentences.py for the full reasoning.
            chunking_tokenizer_fn=split_sentences,
        )

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        heading_stack: list[tuple[int, str]] = []
        acc = _Accumulator()

        def section_path() -> str:
            return " > ".join(text for _, text in heading_stack)

        def flush() -> None:
            if acc.empty:
                return
            chunks.append(
                _build(
                    ordinal=len(chunks),
                    content="\n\n".join(acc.texts),
                    content_type="text",
                    section_path=section_path(),
                    blocks=list(acc.blocks),
                )
            )
            acc.clear()

        for block in document.blocks:
            if block.kind == "heading":
                # A chunk never spans a heading: the text before it belongs to
                # the previous section and must not inherit the new one's path.
                flush()
                level = block.level or 1
                heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
                heading_stack.append((level, block.text))
                continue

            if block.kind == "table":
                flush()
                chunks.append(
                    _build(
                        ordinal=len(chunks),
                        content=block.text,
                        content_type="table",
                        section_path=section_path(),
                        blocks=[block],
                    )
                )
                continue

            block_tokens = count_tokens(block.text)

            if block_tokens > self.target_tokens:
                # A single block too large to fit. Split it on sentence
                # boundaries; every piece keeps the block's geometry, which is
                # the honest answer — we know which block it came from, not
                # where within the block.
                flush()
                for piece in self._splitter.split_text(block.text):
                    chunks.append(
                        _build(
                            ordinal=len(chunks),
                            content=piece,
                            content_type="text",
                            section_path=section_path(),
                            blocks=[block],
                        )
                    )
                continue

            if acc.tokens + block_tokens > self.target_tokens:
                flush()

            acc.blocks.append(block)
            acc.texts.append(block.text)
            acc.tokens += block_tokens

        flush()

        log.info(
            "document_chunked",
            chunks=len(chunks),
            tables=sum(1 for c in chunks if c.content_type == "table"),
            oversized=sum(1 for c in chunks if c.token_count > self.target_tokens),
            mean_tokens=round(sum(c.token_count for c in chunks) / len(chunks), 1) if chunks else 0,
        )
        return chunks


def _build(
    *,
    ordinal: int,
    content: str,
    content_type: str,
    section_path: str,
    blocks: list[ParsedBlock],
) -> Chunk:
    pages = [b.page for b in blocks]
    boxes = [b.bbox for b in blocks if b.bbox is not None]

    bbox: BBox | None = None
    if boxes:
        # A chunk spanning a page break has no single meaningful rectangle, so
        # union only the boxes on its first page. The viewer scrolls to
        # page_start; highlighting a box computed across two pages would put the
        # highlight somewhere neither of them.
        first_page = min(pages)
        on_first = [b.bbox for b in blocks if b.bbox is not None and b.page == first_page]
        if on_first:
            bbox = on_first[0]
            for box in on_first[1:]:
                bbox = bbox.union(box)

    return Chunk(
        ordinal=ordinal,
        content=content,
        content_type=content_type,
        section_path=section_path,
        page_start=min(pages),
        page_end=max(pages),
        token_count=count_tokens(content),
        bbox=bbox,
    )
