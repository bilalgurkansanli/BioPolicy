"""Spot text in a document that is addressed to the system reading it.

Deliberately not a model call. A classifier here would run once per upload, cost
money, add seconds to an ingest that is already the slowest thing a user waits
for, and — the part that matters — would be a second model reading the same
hostile text, which is more attack surface, not less. Regular expressions cannot
be talked out of their job.

This is **not** the defence. The defence is `answer_v2` plus the id
neutralisation in `api/retrieval/context.py`, and the injection set measures
both. This is the part of the problem those cannot solve: telling the user. A
person who uploads a policy prepared by somebody else has a right to know it
contains text aimed at an AI system, and today the only way they would find out
is by noticing that answers about their document read strangely.

What it deliberately does not do:

* **Block the upload.** The document is still a document, its clauses are still
  the user's clauses, and the answering path is tested against exactly this
  material. Refusing the file would fail the user harder than the attack does.
* **Judge the document morally.** "Contains instruction-shaped text" is a fact
  about the bytes. Whether the person who prepared it meant harm is not
  something a regex knows, and the wording surfaced to the user says only what
  was found.
* **Claim completeness.** These patterns catch the phrasings in the injection
  corpus and the obvious neighbours. An attacker who reads this file can write
  around it in a minute. That is acceptable precisely because it is not the
  defence — evading this detector gets you a document that still cannot give the
  answering model orders, only one whose user was not warned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Turkish text arrives with and without diacritics depending on who typed it, so
# every pattern that needs one accepts both. `zekâ`/`zeka`, `talimatı`/`talimati`.
_A = "[aâ]"
_I = "[ıi]"
_S = "[şs]"

# Who the sentence is about, what it forbids, and how far apart they may sit.
#
# `_WITHIN` is "any character that does not end a sentence, except that a dot
# followed by a digit does not end one either" — clause numbers are written
# `4.3` throughout Turkish policy wording, and treating that dot as a full stop
# cuts every such sentence in half.
_ADDRESSEE = r"(cevap|yan" + _I + r"t|kullan" + _I + r"c" + _I + r"|answer|user)"
_OMIT = (
    r"(bahsetme|gösterme|söyleme|belirtme|payla" + _S + r"ma|yazma"
    r"|al" + _I + r"nt" + _I + r"lama"
    r"|do\s+not\s+(mention|cite|quote|reveal|show))"
)
_WITHIN = r"(?:[^.!?]|\.\d)"


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    why: str


RULES: tuple[Rule, ...] = (
    Rule(
        "rule_override",
        re.compile(
            r"(önceki|yukar" + _I + r"daki|tüm)\s+(tüm\s+)?(kural|talimat)\w*\s+"
            r"(iptal|geçersiz|yok\s*say|unut)"
            r"|ignore\s+(all\s+)?(the\s+)?(previous|above|prior)\s+(instruction|rule|prompt)"
            r"|disregard\s+(all\s+)?(previous|above|prior)",
            re.IGNORECASE,
        ),
        "text cancelling the reader's own instructions",
    ),
    Rule(
        "addresses_the_model",
        re.compile(
            r"yapay\s*zek"
            + _A
            + r"|dil\s*model"
            + r"|sistem\s+talimat"
            + r"|asistan"
            + _A
            + r"\s+not"
            + r"|system\s+(prompt|instruction)"
            + r"|(ai|language\s+model)\s+assistant",
            re.IGNORECASE,
        ),
        "text speaking to an AI system rather than to a reader",
    ),
    Rule(
        "forged_context",
        # The prompt's own scaffolding, written into the body of a PDF.
        re.compile(
            r"#\s*Excerpts\s+from\s+the\s+document"
            r"|\[\s*[Cc]\s*\d{1,3}\s*\]"
            r"|\banswer_found\b"
            r"|\bchunk_id\b",
            re.IGNORECASE,
        ),
        "text imitating the structure the model is given its evidence in",
    ),
    Rule(
        "orders_an_omission",
        # Proximity, not keywords. "Bahsetme" alone is ordinary Turkish; next to
        # "cevap" or "kullanıcı" inside one sentence it is an instruction.
        #
        # Two things this got wrong on the first attempt, both found by tests:
        # the window treated the dot in "Madde 4.3" as the end of a sentence, so
        # the most literal example in the corpus slipped through; and it assumed
        # the addressee comes first, which is true in Turkish and false in
        # English ("do not mention … in your answer"). Hence the digit exception
        # and both orderings.
        re.compile(
            f"{_ADDRESSEE}{_WITHIN}{{0,120}}?{_OMIT}|{_OMIT}{_WITHIN}{{0,120}}?{_ADDRESSEE}",
            re.IGNORECASE,
        ),
        "text ordering the reader to leave something out of its answer",
    ),
    Rule(
        "impersonates_us",
        re.compile(
            r"biopolicy[^.!?]{0,80}(geliştirici|gelistirici|ekib|ekip|developer|team)"
            r"|(geliştirici|developer)\s+ekib" + _I + r"\s+taraf" + _I + r"ndan",
            re.IGNORECASE,
        ),
        "text claiming to come from the people who built this system",
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    why: str
    excerpt: str
    """The matched text with a little context, for showing the user where to look."""


def scan(text: str, *, max_findings: int = 8) -> list[Finding]:
    """Return what was found, most important first. Empty means nothing matched.

    Capped, because a document that trips forty patterns tells the user nothing
    more than one that trips three, and an unbounded list would be a way to fill
    a page with our own output.
    """
    findings: list[Finding] = []
    seen: set[str] = set()

    for rule in RULES:
        for match in rule.pattern.finditer(text):
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 60)
            excerpt = " ".join(text[start:end].split())
            key = f"{rule.name}:{excerpt[:60]}"
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(rule=rule.name, why=rule.why, excerpt=excerpt))
            break  # One example per rule is enough to make the point.

    return findings[:max_findings]
