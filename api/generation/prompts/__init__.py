"""Versioned prompt templates.

Prompts are code. They are stored as files, loaded by name and version, and the
version that produced an answer is written to `messages.prompt_version` — so a
number in `eval/report.md` can always be traced back to the exact instructions
that produced it. A metric without a prompt version attached is not reproducible.

Changing a prompt means bumping to `_v2` and re-running the eval, not editing
`_v1` in place. The old file stays so an old result stays explicable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

_DIR = Path(__file__).parent

ANSWER = "answer_v1"
VERIFY = "verify_v1"
REWRITE = "rewrite_v1"


@lru_cache(maxsize=16)
def load(name: str) -> str:
    """Load a prompt template by versioned name, e.g. `answer_v1`."""
    path = _DIR / f"{name}.md"
    if not path.exists():
        available = sorted(p.stem for p in _DIR.glob("*.md"))
        raise FileNotFoundError(f"No prompt named {name!r}. Available: {', '.join(available)}")
    return path.read_text(encoding="utf-8").strip()


def render(name: str, **values: str) -> str:
    """Load a template and substitute `$placeholders`.

    WHY `string.Template` and not `str.format`: every one of these prompts ends
    with a JSON output example, and JSON is made of braces. With `str.format`
    each of those braces would have to be doubled, which makes the example in
    the file stop looking like the JSON we are asking the model to produce —
    and a prompt you cannot read is a prompt you will get wrong. `$name` does
    not collide with anything in JSON.
    """
    try:
        return Template(load(name)).substitute(**values)
    except KeyError as exc:
        raise KeyError(f"Prompt {name!r} needs a value for {exc}") from exc


def available() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.md"))
