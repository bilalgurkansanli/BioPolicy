"""One line per evaluation run, appended forever.

A report is a photograph. It says what was true on the day it was produced, and
says nothing at all about whether a number moved because of the change that was
just made or because the model was having a different afternoon.

This file is the record that makes the difference visible. It is append-only and
it is committed, so a reviewer can see whether refusal accuracy has been steady
at 100% across nine runs or has been oscillating between 86% and 100% while the
report happened to be regenerated on a good day.

## Why JSON Lines and not a table in the report

The report is rendered from the *current* results and rewritten in place. Any
history kept inside it would be rewritten too. A separate append-only file is
the only shape where adding today's row cannot disturb last month's.

Rows are never edited. A run that produced bad numbers stays in the file — that
is the entire value of keeping one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from eval.metrics import Report

HISTORY_PATH = Path(__file__).parent / "results" / "history.jsonl"


@dataclass(frozen=True, slots=True)
class HistoryRow:
    """What is worth keeping about one arm of one run.

    Deliberately narrow. Every field here is a headline number that appears in
    the report; the per-question detail already lives beside it in the arm's own
    results file, and duplicating it would make the history unreadable at
    exactly the size where it starts being useful.
    """

    run_at: str
    commit: str
    question_set: str
    arm: str
    questions: int
    model: str
    prompt: str
    """The answering prompt version.

    Added after a run where the prompt changed and the headline numbers did
    not: the chart drew a flat line across a real change, which is the one
    thing a history file exists to prevent. A row without it cannot answer
    "was that the same system?"
    """
    refusal_accuracy: float
    false_refusal_rate: float
    balanced_accuracy: float
    recall_at_k: float
    citation_validity: float
    suppressed: int
    cost_per_question: float

    def as_dict(self) -> dict[str, object]:
        return {
            "run_at": self.run_at,
            "commit": self.commit,
            "set": self.question_set,
            "arm": self.arm,
            "questions": self.questions,
            "model": self.model,
            "prompt": self.prompt,
            "refusal_accuracy": round(self.refusal_accuracy, 4),
            "false_refusal_rate": round(self.false_refusal_rate, 4),
            "balanced_accuracy": round(self.balanced_accuracy, 4),
            "recall_at_k": round(self.recall_at_k, 4),
            "citation_validity": round(self.citation_validity, 4),
            "suppressed": self.suppressed,
            "cost_per_question": round(self.cost_per_question, 6),
        }


def row_from(
    report: Report,
    *,
    commit: str,
    question_set: str,
    arm: str,
    model: str,
    prompt: str,
) -> HistoryRow:
    return HistoryRow(
        run_at=datetime.now(UTC).isoformat(timespec="seconds"),
        commit=commit,
        question_set=question_set,
        arm=arm,
        questions=report.total,
        model=model,
        prompt=prompt,
        refusal_accuracy=report.refusal.refusal_accuracy,
        false_refusal_rate=report.refusal.false_refusal_rate,
        balanced_accuracy=report.refusal.balanced_accuracy,
        recall_at_k=report.retrieval.recall_at_k,
        citation_validity=report.citations.validity,
        suppressed=report.citations.suppressions,
        cost_per_question=report.cost.mean_cost_per_query_usd,
    )


def append(rows: list[HistoryRow], *, path: Path = HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.as_dict(), ensure_ascii=False) + "\n")


def load(path: Path = HISTORY_PATH) -> list[dict[str, object]]:
    """Every row ever written, oldest first.

    A malformed line is skipped rather than fatal: this file is append-only and
    a truncated final write should not make the whole history unreadable.
    """
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
