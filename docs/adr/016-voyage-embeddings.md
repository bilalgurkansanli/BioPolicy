# ADR 016 — Embeddings move to Voyage

**Status:** accepted · **Date:** 2026-08-10

## Context

The first real document anyone uploaded — a 27-page AXA home policy — could not
be ingested. Not because of parsing, chunking or cost, but because of the shape
of Google's free-tier quota for `gemini-embedding-001`:

    Quota exceeded for metric: embed_content_free_tier_requests, limit: 1000
    quotaId: EmbedContentRequestsPerDayPerProjectPerModel-FreeTier

The quota counts **passages, not requests**. The policy is 132 of them, so the
allowance is about seven documents a day. That is not a demo, and it is not a
limit that pacing, batching or retrying can move: it is a wall, not a window.

Cost was never the problem. The same document embeds for $0.006.

## Why not Anthropic

The obvious question, asked directly: the project already pays Anthropic for
Haiku, so why not embed there too. Anthropic has no embedding endpoint. Its
client exposes `messages`, `completions` and `models` — verified rather than
assumed:

    >>> hasattr(anthropic.Anthropic(api_key="x"), "embeddings")
    False

Their own documentation points at Voyage for vectors. Producing an embedding and
producing an answer are different services, and one provider offering the second
does not make it offer the first.

## Why not drop embeddings entirely

Measured before deciding, because it is the option that removes a dependency
rather than adding one. Retrieval was run over the golden set with the vector
arm switched off, keyword search alone:

| retrieval | recall@8 |
|---|---|
| hybrid (vector + keyword) | 98% |
| keyword only | 86% |

Seven of 49 answerable questions lose the clause they need, and on five of them
the keyword arm returns nothing at all. The losses are exactly what the hybrid
design exists for: a reader types "sel hasarı" and the policy says "su baskını".
Twelve points of recall is too much to pay for one fewer vendor.

## Decision

Embeddings move to **`voyage-4-lite` at 1024 dimensions**.

| | Gemini | Voyage |
|---|---|---|
| free allowance | 1,000 passages/day | 200M tokens, one-off |
| price after | $0.15 / 1M tokens | $0.02 / 1M tokens |
| usage reported | `billable_character_count` | `usage.total_tokens` |
| vectors | need renormalising after truncation | unit-length already |

The 27-page policy is 36K tokens against that 200M allowance.

Two secondary gains matter more than they look. Voyage reports **tokens**, which
is the unit its rate card uses, so an ingest can finally be priced and recorded —
Gemini reported characters against a per-token price, and the ratio between them
was a number this project would not invent, which is why embedding spend was
invisible to the budget breaker. And its vectors arrive unit-length, so there is
no renormalisation step that could quietly change ranking if migration 0003's
index metric were ever changed from cosine.

### 1024 dimensions

Voyage offers 256, 512, 1024 and 2048. pgvector's HNSW index tops out at 2000,
so 2048 is unusable and 1024 is the largest that fits. It is also a width
`gemini-embedding-001` can produce, which is deliberate: the fallback embedder
still matches the column, so a deployment that switches providers fails at
insert time rather than writing subtly wrong distances.

### Gemini is kept as a fallback

Not deleted, and still tested. `build_embedder` picks Voyage when
`VOYAGE_API_KEY` is set and Gemini otherwise, logging which it chose. A provider
swap that leaves no way back is not a swap, it is a bet.

It is a choice, not a failover chain. One document's vectors must all come from
one model — a vector is only meaningful in the space that produced it — so the
provider is chosen once at startup and stays chosen.

## Consequences

**Every stored vector was invalid and had to go.** Migration 0012 deletes the
chunks, widens the column and rebuilds the HNSW index. There is no conversion
between embedding spaces: the same clause under two models lands in two
unrelated places, and querying old rows with new query vectors would not error —
it would return confident, arbitrary results, which is the worst failure mode a
retrieval system has.

**Free-tier pacing is different, not absent.** Voyage limits by tokens per
minute, and an account with no payment method on file gets 3 requests and 10K
tokens a minute. The policy takes about four minutes on that allowance, which is
fine — ingestion is a background job behind a progress indicator. Adding a
payment method lifts the ceiling and still spends nothing until the 200M free
tokens are gone.

**A third vendor.** The project now depends on Anthropic, Google and Voyage. No
new package: Voyage is three fields over HTTP through `httpx`, which was already
a dependency (ADR 002 keeps the dependency list short and licence-checked).

## What this did not fix

The policy now ingests — 132 chunks, all 28 coverage amounts present — and its
schedule is still hard to retrieve. The table is set without ruled lines, so
pdfplumber does not detect it as a table and it arrives as prose: a row of
`*BİNA YANGIN 3.630.000,00 91,77`. As a data dump it embeds poorly against a
natural-language question, and its density hurts it in `ts_rank_cd` too, so it
ranks 5th on one phrasing of the question and off the list on another.

That is a table-extraction problem, not an embedding one, and it is the next
thing worth measuring.
