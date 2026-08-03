# ADR 003 — LlamaIndex is used for node parsing and nothing else

- **Status:** accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

LlamaIndex will happily run this entire application. It has vector store
integrations for Supabase, retrievers, query engines, chat engines with memory,
response synthesisers, and a citation query engine that does something close to
what Section 7 describes. Using it end-to-end would cut days off the build.

Two reasons not to. The first is stated in the spec: retrieval, prompting and
generation are the parts I am building this to learn, and a framework that hides
them defeats the exercise. The second is more concrete — the anti-hallucination
layer needs behaviour no framework gives you off the shelf: citation IDs that
survive into the prompt and back out, a verification pass that is deliberately
denied the original question, and three independently switchable mechanisms so
the eval harness can ablate them one at a time.

## Decision

`llama-index-core` is a dependency for its **node parsers only** —
`MarkdownNodeParser` and the sentence splitter. No vector store integration, no
retriever, no query engine, no chat engine, no LLM adapter. Nothing else from
the package may be imported; `retrieval/` and `generation/` are hand-written
against raw SQL and the provider SDKs directly.

## Consequences

**Bought:** heading-aware, token-aware chunking that is genuinely fiddly to get
right, for one small pure-Python dependency. Full control and full visibility
over every prompt, every SQL query and every scoring decision — which is what
makes the ablation table in Section 11 possible at all.

**Cost:** more code to write and own. Retry logic, batching, streaming and
provider failover are all hand-rolled where a framework would have supplied
them. If `llama-index-core` changes its node parser API, the chunker breaks and
there is no abstraction layer absorbing it.

**Enforcement:** this is a rule that decays silently under deadline pressure —
one convenient import at 1am and the boundary is gone. `api/tests/` carries a
test asserting that nothing outside `api/ingest/chunker.py` imports
`llama_index`, so the boundary fails CI instead of eroding.

## Alternatives considered

**Full LlamaIndex.** Fastest path to a working demo. Rejected: it hides exactly
the layer this project exists to demonstrate, and its citation support is close
enough to Section 7 to be tempting while not actually doing the quote
verification that makes the mechanism worth anything.

**No LlamaIndex at all — hand-write the chunker too.** Considered seriously.
Markdown-aware recursive splitting with token budgets and overlap is a solved
problem with unpleasant edge cases, and hand-writing it would consume Phase 1
time that Section 7 needs more. The dependency is pure Python and adds no
meaningful image weight.

**LangChain's text splitters instead.** Equivalent capability. No reason to
prefer it, and the spec names LlamaIndex.
