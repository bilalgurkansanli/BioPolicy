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

## The failure this warning describes, one hour later

The paragraph above about querying old rows with new query vectors was written
while a second copy of the provider choice sat in `api/scripts/ask.py`. It built
its own `GeminiEmbedder` rather than calling `build_embedder` — harmless with one
provider, a silent correctness bug with two. The CLI embedded questions with
Gemini and compared them against chunks embedded with Voyage.

The symptom pointed somewhere else entirely. Asked for a figure plainly present
in the policy, the system refused, and the coverage schedule was absent from the
retrieved context — so the schedule looked like the problem: a table set without
ruled lines, arriving as prose, embedding poorly as a data dump. A whole
investigation into borderless table extraction started from that.

Measuring retrieval directly ended it. Through the store, on the same question
the CLI could not answer, the schedule ranked **first** in both arms. Nothing
was wrong with the table. With the embedders matched, "Bina yangın bedeli kaç
TL?" returns 3.630.000,00 TL citing `BİNA YANGIN 3.630.000,00` verbatim at
groundedness 1.00.

The lesson is narrower than "test more": a provider choice must exist in exactly
one place. Two call sites had copied it, and both were fixed by routing through
`build_embedder`.

## What is still true about the tables

The schedule is retrieved and cited correctly, but it arrives as prose rather
than as a Markdown table, because pdfplumber's line-based detection finds
nothing on a borderless layout. The text strategy is not a drop-in replacement —
measured on this document it reads a whole page as a 95×10 grid, 22% of cells
filled, splitting the letterhead across columns.

It is working, so it is a quality item rather than a defect: structure would
help a model read which figure belongs to which peril on a wider table than
this one.
