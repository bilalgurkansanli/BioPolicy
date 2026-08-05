# ADR 010 — Stage events, not token streaming

- **Status:** accepted
- **Date:** 2026-08-04
- **Phase:** 4

## Context

Section 8 of the spec defines the chat endpoint as an SSE stream carrying, in
order: `retrieval_started` → `retrieval_complete` → `token` (many) →
`verification` → `done`. Streaming tokens as they arrive is the expected shape
for a chat product, and users read a streaming answer as responsive.

Two things in this system make that shape impossible to implement honestly.

**1. The answer is structured output, not prose.** The model returns a single
JSON object — `answer_found`, `answer`, `citations`, `confidence`, `caveats` —
enforced by a provider-level schema. Streaming its tokens streams JSON syntax.
Reconstructing readable prose from a partial JSON document means parsing
half-written strings and guessing where the `answer` field ends; every escape
sequence and every truncation is a chance to render something the model did not
say.

**2. An answer that streams cannot be suppressed.** This is the fatal one.
Citation binding and self-verification both run *after* generation and can
withhold the answer entirely — that is the product's central mechanism. If the
answer has already been streamed into the user's view word by word, there is
nothing left to withhold. The best available behaviour is to retract text the
user has already read, which is worse than never showing it: a retraction still
leaves the claim in their head, and it advertises that the system shows unverified
output by default.

A system whose thesis is "we would rather show you nothing than something
unverified" cannot also show you things before it has verified them.

## Decision

`POST /api/chat` streams **stage events**, not tokens:

    retrieval_started
    retrieval_complete   { chunk_ids, count }
    answering
    verifying            (omitted when verification is disabled)
    done                 { answer, citations, refused, groundedness, usage }
    error                { code, message }

The answer text arrives once, in `done`, after every check has run. No `token`
event is emitted and the client must not expect one.

## Consequences

**Bought:** the suppression path actually works. An answer that fails binding or
scores below the groundedness floor is never seen, rather than being seen and
then withdrawn. The JSON is parsed once, completely, by code that can reject it.

**Cost, and it is a real one:** the user waits with no text on screen for the
whole generation — measured at 6.0s median and 9.9s at p95 on the evaluation
set. That is a worse felt experience than a stream, and pretending otherwise
would be dishonest. The mitigation is that the stage events are real: the UI
shows "searching the document", then "drafting an answer", then "checking the
answer against the document", each backed by an actual pipeline stage rather
than a spinner with invented labels. Users tolerate a wait they can see the
shape of.

**Revisit if:** we add a mode where verification is disabled by configuration.
In that mode there is nothing to suppress after binding, and token streaming
becomes defensible — but it would be a different product, and the streaming
behaviour should follow the guarantee rather than the other way round.

## Alternatives considered

**Stream tokens, then retract on suppression.** Rejected in Context: a retracted
claim is still a delivered claim, and the retraction teaches users that what
they see is provisional.

**Stream tokens but hold the last sentence back.** A half-measure that inherits
the partial-JSON problem and still shows most of an answer that may be
withheld.

**Two passes: stream a prose answer, then structure and verify it.** Gives real
streaming and keeps the guarantee. Rejected on cost — it doubles the generation
calls, and generation is already the largest line item against a $30 ceiling.
Worth reconsidering if the budget ever stops being the binding constraint.

**Stream the verifier's progress instead.** Considered as a way to fill the
silence with something true. It arrives after the wait that matters, so it fills
the wrong gap.
