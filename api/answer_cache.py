"""Answers, remembered — and always labelled as remembered.

## What this is for

Three sample documents, three suggested questions each, and every visitor asked
the same nine. Each one was a retrieval, an answer call and a verification call
producing a paragraph identical to the one produced a minute earlier. The demo's
most repeated operation was also one of its most expensive.

## The rule that makes it honest

**A cached answer is never presented as a fresh one.** The response carries
`cached: true` and the interface says so. This matters more here than in most
systems, because the thing on display is a measurement: an answer served in 40ms
for $0 would otherwise quietly contradict the latency and cost figures in
`eval/report.md`, which are measurements of real calls.

## Samples only, and why that is not a limitation

Cache entries are shared across users — two people asking the same question of
the same document get the same paragraph, because the answer is a property of
the document. That is only safe for documents that are themselves shared. An
uploaded policy belongs to one account, lives 24 hours, and would be asked its
questions once; caching it would add a way for one account's answer to reach
another in exchange for no hit rate at all.

So the guard is a positive check on `is_sample`, applied on both read and write.
Not because the key would collide — a document id is in it — but because a cache
whose safety rests on a key being unguessable is one bug away from not being
safe, while one that refuses to store private documents is safe by construction.

## What invalidates an entry

The prompt version and the model are part of the key. A prompt change therefore
misses every entry instead of invalidating them: same effect, no sweep, and no
window in which a retired prompt's answers are still being served. Editing
`answer_v2.md` without renaming it is the one case this does not catch, which is
also the case ADR 012 already forbids.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from api.logging_config import get_logger

log = get_logger(__name__)

# Entries older than this are ignored on read, whatever the sweep has done.
# The sample documents do not change, so this is not about staleness of content;
# it is a ceiling on how long a bug in what we cached can keep being served.
MAX_AGE_HOURS = 24 * 7


def fingerprint(question: str, language: str) -> str:
    """A stable key for a question, in one language.

    Normalisation is case folding and whitespace collapse. Nothing else — no
    stemming, no stop-word removal, no punctuation stripping. "Deprem limiti
    nedir?" and "Deprem limiti ne kadar?" are different questions, and a cache
    that treats them as one answers the wrong one. Over-collapsing is a
    correctness bug wearing a hit-rate improvement's clothes.

    Turkish makes the case fold worth stating: `str.lower()` maps I to ı in a
    locale-aware editor's head but not in Python, and `casefold` is at least
    consistent about it. Both spellings of a question normalise to the same
    thing as long as the caller does not mix them, and the hash is only ever
    compared with itself.
    """
    text = unicodedata.normalize("NFC", question).casefold()
    collapsed = " ".join(text.split())
    return hashlib.sha256(f"{language}\x00{collapsed}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CachedAnswer:
    payload: dict[str, Any]
    served_before: int
    """How many times this entry has been served, before this one."""


class AnswerCache:
    def __init__(self, pool: asyncpg.Pool, *, enabled: bool = True) -> None:
        self._pool = pool
        self._enabled = enabled

    async def get(
        self,
        *,
        document_id: UUID,
        question: str,
        language: str,
        prompt_version: str,
        model: str,
    ) -> CachedAnswer | None:
        """Look up an answer, and record that it was served.

        Returns `None` for anything that is not a hit, including every error:
        a cache that can fail a request has stopped being an optimisation.
        """
        if not self._enabled:
            return None

        try:
            row = await self._pool.fetchrow(
                """
                update answer_cache c
                   set serve_count = c.serve_count + 1,
                       last_served_at = now()
                  from documents d
                 where d.id = c.document_id
                   and c.document_id = $1
                   and c.question_hash = $2
                   and c.prompt_version = $3
                   and c.model = $4
                   and c.created_at > now() - ($5 || ' hours')::interval
                   -- The sample check is repeated here rather than trusted from
                   -- the write path: a row that should never have been stored
                   -- must not be servable either.
                   and d.is_sample
                returning c.payload, c.serve_count
                """,
                document_id,
                fingerprint(question, language),
                prompt_version,
                model,
                str(MAX_AGE_HOURS),
            )
        except Exception as exc:
            log.warning("answer_cache_read_failed", error=str(exc))
            return None

        if row is None:
            return None

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        # `serve_count` is post-increment, so the count *before* this serve is
        # one less. The interface shows it, and an off-by-one there is a wrong
        # number on screen rather than a harmless internal detail.
        return CachedAnswer(payload=payload, served_before=int(row["serve_count"]) - 1)

    async def put(
        self,
        *,
        document_id: UUID,
        question: str,
        language: str,
        prompt_version: str,
        model: str,
        payload: dict[str, Any],
    ) -> None:
        """Store an answer. Never raises — the answer is already produced."""
        if not self._enabled:
            return

        try:
            await self._pool.execute(
                """
                insert into answer_cache (
                    document_id, question_hash, prompt_version, model, payload
                )
                select $1, $2, $3, $4, $5
                 where exists (select 1 from documents d where d.id = $1 and d.is_sample)
                on conflict (document_id, question_hash, prompt_version, model)
                do update set payload = excluded.payload, created_at = now()
                """,
                document_id,
                fingerprint(question, language),
                prompt_version,
                model,
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception as exc:
            log.warning("answer_cache_write_failed", error=str(exc))


def is_cacheable(payload: dict[str, Any]) -> bool:
    """Whether an answer is one worth remembering.

    Three kinds are not.

    A **suppressed** answer is the output of a check that failed, and the model
    is not deterministic: the next attempt may well produce a groundable answer.
    Caching the failure would make one bad sample permanent and would freeze the
    demo's most interesting behaviour into a fixture.

    A **provider error** is a refusal with no reasoning behind it — the text is
    "try again shortly", and caching it would mean the retry never happens.

    An answer with **no citations** is either of those in disguise, or a refusal.
    A refusal is a real outcome, but it is also the outcome most likely to change
    when retrieval improves, and it is the cheap path anyway.
    """
    if payload.get("suppressed"):
        return False
    if payload.get("refused"):
        return False
    return bool(payload.get("citations"))
