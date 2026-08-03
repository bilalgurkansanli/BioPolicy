"""Bilingual sentence splitting for Turkish and English.

## Why this exists rather than NLTK

`SentenceSplitter` reaches for NLTK's punkt tokenizer by default. Three problems,
in increasing order of importance:

1. **It breaks under the standard `uv` layout.** NLTK ships an import guard that
   refuses any import resolving under `Path.cwd()`. Because `uv` creates `.venv`
   *inside* the project directory, every installed package resolves under the
   CWD, so NLTK blocks its own dependency (`regex`) the moment a test runs from
   the repo root. Setting `PYTHONSAFEPATH` does not help — the guard tests the
   file's location, not `sys.path`.

2. **punkt is a runtime download.** On a scale-to-zero container that is either
   a cold-start network fetch or a bundled data blob, and the whole parsing
   strategy (ADR 002) exists to keep the image small.

3. **punkt is trained on English.** Half this corpus is Turkish, where it offers
   nothing over a decent regex.

So we own this. It is roughly forty lines, it has no data files, and it can be
tested directly against the documents it will actually see.

## The failure mode that matters

Turkish writes large numbers as `2.500.000` and dates as `01.03.2026`. Every one
of those dots is a sentence boundary to a naive splitter. Getting this wrong
does not throw — it silently severs `Deprem ve Yanardağ Püskürmesi` from
`1.800.000`, which is precisely the corruption the chunker exists to prevent.
"""

from __future__ import annotations

import re

# Abbreviations that end in a period without ending a sentence. Compared
# case-insensitively against the token preceding the candidate boundary.
_ABBREVIATIONS: frozenset[str] = frozenset(
    {
        # Turkish
        "md",
        "bkz",
        "vb",
        "vs",
        "sn",
        "dr",
        "av",
        "prof",
        "doç",
        "yrd",
        "no",
        "tel",
        "sok",
        "cad",
        "mah",
        "apt",
        "bl",
        "örn",
        "yy",
        "age",
        "krş",
        # English
        "mr",
        "mrs",
        "ms",
        "st",
        "ltd",
        "inc",
        "co",
        "corp",
        "plc",
        "approx",
        "etc",
        "eg",
        "ie",
        "cf",
        "al",
        "fig",
        "para",
        "sec",
        "art",
        "pp",
        "vol",
    }
)

# A candidate boundary: sentence-ending punctuation, optional closing quotes or
# brackets, then whitespace.
_CANDIDATE = re.compile(r"[.!?…]+[\"'’”)\]]*\s+")

# What a real next sentence may start with. Bullets are included because policy
# exclusions arrive as "…benzeri haller. • 4.2 Nükleer yakıt…" once list markers
# have been flattened into prose.
_STARTS_SENTENCE = re.compile(r"[A-ZÀ-ÖØ-ÞĞİÖŞÜÇ0-9•\-–—\"'“(\[]")

# The token immediately before the boundary, without its trailing punctuation.
_TRAILING_TOKEN = re.compile(r"([\wÀ-ÿĞğİıÖöŞşÜüÇç]+)[.!?…]+[\"'’”)\]]*\s*$")


def _is_real_boundary(text: str, dot_index: int, next_index: int) -> bool:
    if next_index >= len(text):
        return False
    if not _STARTS_SENTENCE.match(text[next_index]):
        return False

    before = text[: dot_index + 1]
    match = _TRAILING_TOKEN.search(before)
    if match is None:
        return True

    token = match.group(1)

    # "Ltd." / "vb." / "Md." — an abbreviation, not a sentence end.
    if token.lower() in _ABBREVIATIONS:
        return False

    # A single letter is an initial: "A. Şanlı", "J. Smith".
    if len(token) == 1 and token.isalpha():
        return False

    # A bare number before the dot is a list marker or an ordinal — "Madde 4."
    # or "2." — and the digits that follow belong with it. Note that grouped
    # numbers like 2.500.000 never reach here: they contain no whitespace after
    # the dot, so `_CANDIDATE` does not match them in the first place.
    if token.isdigit() and text[next_index].isdigit():
        return False

    return True


def split_sentences(text: str) -> list[str]:
    """Split `text` into sentences. Never returns empty strings."""
    stripped = text.strip()
    if not stripped:
        return []

    sentences: list[str] = []
    start = 0
    for match in _CANDIDATE.finditer(stripped):
        if _is_real_boundary(stripped, match.start(), match.end()):
            piece = stripped[start : match.end()].strip()
            if piece:
                sentences.append(piece)
            start = match.end()

    tail = stripped[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences or [stripped]
