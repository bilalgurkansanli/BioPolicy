"""Loading and validating the golden dataset.

`expected_evidence` is text, not chunk ids. Chunk UUIDs are regenerated on every
ingest, so a golden set keyed on them breaks the first time the document is
re-ingested or the chunk size is retuned — and it breaks *silently*, by scoring
every question as a retrieval miss. Text spans survive both.

The validation here is what keeps the dataset honest as the documents evolve.
If someone edits `sample_content.py` and a planted fact moves or changes wording,
`validate()` fails loudly rather than letting the eval quietly measure a
question whose expected answer no longer exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from eval.sample_content import ALL_DOCUMENTS, HARD_DOCUMENTS

GOLDEN_PATH = Path(__file__).parent / "golden" / "questions.json"

Category = Literal["factual", "table", "multi_clause", "negative", "cross_lingual"]
# "contradiction" only occurs in the hard set: a question the document answers
# twice, incompatibly. It is not a negative — the document does address it — and
# it is not an ordinary factual, because there is no single right answer to
# give. Keeping it as its own category is what lets the report say how many
# there were and what happened to them.
VALID_CATEGORIES: frozenset[str] = frozenset(
    {"factual", "table", "multi_clause", "negative", "cross_lingual", "contradiction"}
)


@dataclass(frozen=True, slots=True)
class GoldenQuestion:
    id: str
    document: str
    lang: str
    category: str
    question: str
    expected_answer_found: bool
    expected_evidence: tuple[str, ...]
    expected_answer_summary: str
    notes: str = ""

    @property
    def is_negative(self) -> bool:
        return not self.expected_answer_found


def load(path: Path = GOLDEN_PATH) -> list[GoldenQuestion]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenQuestion(
            id=item["id"],
            document=item["document"],
            lang=item["lang"],
            category=item["category"],
            question=item["question"],
            expected_answer_found=item["expected_answer_found"],
            expected_evidence=tuple(item.get("expected_evidence", ())),
            expected_answer_summary=item.get("expected_answer_summary", ""),
            notes=item.get("notes", ""),
        )
        for item in raw["questions"]
    ]


def document_text(slug: str) -> str:
    """Everything a document says, flattened to one searchable string.

    Built from `sample_content.py` rather than from the parsed PDF, for two
    reasons: it is the actual source of truth for what the document contains,
    and it works for the scanned sample, which cannot be parsed at all without
    an OCR provider.
    """
    doc = next((d for d in (*ALL_DOCUMENTS, *HARD_DOCUMENTS) if d["slug"] == slug), None)
    if doc is None:
        raise KeyError(f"No sample document named {slug!r}")

    parts: list[str] = [doc["title"], doc["subtitle"]]
    parts += [f"{k} {v}" for k, v in doc["meta"]]

    for kind, payload in doc["blocks"]:
        if kind in {"h1", "h2", "p"}:
            parts.append(str(payload))
        elif kind == "list":
            parts.extend(str(item) for item in payload)
        elif kind == "table":
            for row in payload:
                parts.append(" | ".join(str(cell) for cell in row))

    return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class Stats:
    total: int
    by_category: dict[str, int]
    by_language: dict[str, int]
    by_document: dict[str, int]
    negative_share: float


def stats(questions: list[GoldenQuestion]) -> Stats:
    def tally(key: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for question in questions:
            counts[key(question)] = counts.get(key(question), 0) + 1
        return dict(sorted(counts.items()))

    negatives = sum(1 for q in questions if q.is_negative)
    return Stats(
        total=len(questions),
        by_category=tally(lambda q: q.category),
        by_language=tally(lambda q: q.lang),
        by_document=tally(lambda q: q.document),
        negative_share=negatives / len(questions) if questions else 0.0,
    )


def validate(questions: list[GoldenQuestion]) -> list[str]:
    """Return a list of problems. Empty means the dataset is coherent."""
    problems: list[str] = []
    # Both sets, because the hard questions are validated by the same function
    # and a document it has never heard of reads as a typo in the question file.
    slugs = {d["slug"] for d in (*ALL_DOCUMENTS, *HARD_DOCUMENTS)}
    seen: set[str] = set()

    texts = {slug: document_text(slug) for slug in slugs}

    for question in questions:
        if question.id in seen:
            problems.append(f"{question.id}: duplicate id")
        seen.add(question.id)

        if question.document not in slugs:
            problems.append(f"{question.id}: unknown document {question.document!r}")
            continue

        if question.category not in VALID_CATEGORIES:
            problems.append(f"{question.id}: unknown category {question.category!r}")

        if question.lang not in {"tr", "en"}:
            problems.append(f"{question.id}: unexpected language {question.lang!r}")

        if not question.expected_answer_summary:
            problems.append(f"{question.id}: missing expected_answer_summary")

        if question.is_negative:
            if question.expected_evidence:
                problems.append(
                    f"{question.id}: a negative must have no expected_evidence — "
                    "if there is evidence, the document answers it"
                )
            if question.category != "negative":
                problems.append(
                    f"{question.id}: expected_answer_found is false but category is "
                    f"{question.category!r}"
                )
        else:
            if not question.expected_evidence:
                problems.append(f"{question.id}: an answerable question needs expected_evidence")

            # The check that actually catches drift: the evidence must exist.
            haystack = texts[question.document]
            for span in question.expected_evidence:
                if span not in haystack:
                    problems.append(
                        f"{question.id}: evidence {span!r} does not appear in "
                        f"{question.document} — the document changed, or the span is a typo"
                    )

    return problems
