# ADR 014 — The entailment check: built, measured, switched off

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 8

## Context

The 2×2 ablation in `eval/report.md` produced the most useful result this
project has had: **citation binding and self-verification changed no decisions**
while adding roughly 55% to the cost of every question. The strict prompt did
all the work.

The report also diagnosed why, and the diagnosis was specific enough to act on:

> The naive prompt's errors are *correct citations supporting an unwarranted
> inference*: asked whether a stolen car is covered, it quotes the theft clause
> accurately and then concludes the car is included. Binding checks that the
> quote is real — it is. Verification checks the claim against the excerpt — the
> excerpt does say theft is covered. Neither mechanism is built to catch a valid
> quote used to support a conclusion the document never draws.

That is a well-formed engineering problem, so it got a fourth mechanism.

## What was built

`api/generation/entailment.py`, with `answer_v1`'s sibling prompt `entail_v1`.

It asks one question: **do the excerpts settle the question, or merely discuss
something near it?** Verdicts are `ENTAILED`, `RELATED_ONLY`, `CONTRADICTED`,
`UNSURE`. Only the first two decide anything: `RELATED_ONLY` and `CONTRADICTED`
withhold the answer, while `UNSURE` serves it — a checker admitting it cannot
tell must not become a censor.

The design turns on one difference from the verifier. `api/generation/verifier.py`
is deliberately **not** shown the question, because a verifier that knows the
question drifts toward judging whether the answer responds *well*. That decision
is also exactly why it cannot see this failure: "is the car covered?" answered
with "theft is covered" decomposes into a claim the excerpt supports. The
unwarranted step lives in the relation between question and answer, which the
verifier is blind to by design. This check is its complement — two passes, two
blind spots, arranged so neither shares the other's.

## What the measurement said

Two new arms, `naive_entailed` and `strict_entailed`, over the same 70 questions.

| | refusal accuracy | false-refusal | balanced | cost |
|---|---:|---:|---:|---:|
| strict + mechanisms (shipped) | 100% | 2% | 99% | — |
| strict + mechanisms + entailment | 100% | 4%\* | 98% | +24% |
| naive + mechanisms | 86% | 0% | 93% | — |
| naive + mechanisms + entailment | 81% | 4%\* | 88% | +24% |

\* after subtracting provider errors, of which more below.

**It caught nothing.** Refusal accuracy did not move in either arm. The
mechanism built to catch unwarranted inference did not catch any, on the corpus
whose failures were unwarranted inference.

**It cost something.** A few points of false refusals, 24% on every question,
and — because it is a third *serial* provider call — two questions per run
failing with provider overload errors that the two-call arms did not have. A
reliability regression is a cost even when the reliability is somebody else's.

## What the adversarial set said, which is different

The same run over `eval/golden/questions_hard.json`, twelve questions across a
self-contradicting policy and a two-column layout:

On `hard-cel-002` — a surgery limit stated as 100.000 TL in the schedule and
75.000 TL in the article text — the shipped configuration **answered**, picking
one figure and citing it correctly. With the entailment check the answer was
**withheld**, with the reason:

> Excerpt C2 table states the surgery limit is 100.000 TL, but C1 states it is
> 75.000 TL. The drafted answer cites the higher figure without resolving this
> conflict.

That is the failure this product exists to prevent, caught by nothing else in
the pipeline, on a document written to resemble a real one.

By the binary metric the check still scored *worse* on that set — 90% balanced
against 95% — because the metric has no way to represent "correctly declined
because the document contradicts itself." The metric is too coarse for the case,
and saying so is more honest than adjusting it until it agrees.

## Decision

**The mechanism ships in the code and is off by default.**

`ENABLE_ENTAILMENT_CHECK=false`. One environment variable turns it on, the
evaluation harness has an arm for it, and the tests pin its behaviour.

The reasoning is the project's own standard applied to itself. Mechanisms are
justified by measurement, and the measurement available says: no decisions
changed, 24% added to every question, and a reliability cost. A single caught
contradiction on a document written by hand to contain one is evidence that the
check *can* work — it is not evidence about how often real policies contradict
themselves, and paying 24% on every question against a frequency nobody has
measured is exactly the reasoning this report exists to argue against.

## Consequences

**Bought:** the diagnosis in the report is now a thing that was tried rather
than a thing that was suggested, with numbers on both sides. The check is one
variable away for anyone whose documents look like the adversarial set.

**Cost:** a mechanism nobody runs is a mechanism that rots. It is covered by
thirteen tests and by an evaluation arm, which is the most that can be done
short of shipping it.

**The uncomfortable part:** mechanisms 2 and 3 also changed no decisions on this
corpus, and they *are* on. That is not consistent. The defence is that they cost
nothing in reliability — no extra serial call — and that citation binding is
what makes the citation chips clickable at all, which is a product feature and
not only a safety check. It is a weaker defence than it looks, and the honest
version is that the bar was raised for the fourth mechanism because the third
had already taught us to be suspicious.

**Revisit when:** there is a corpus of real documents. The question the demo set
cannot answer is how often a policy contradicts itself, and the entire decision
above turns on that number.

## Alternatives considered

**Ship it on.** Rejected: it would mean the report says a mechanism changed no
decisions while the code pays for it on every question, which is the exact
pattern this project criticised in its own earlier arms.

**Run it only when retrieval returns clauses that disagree.** The right shape,
probably — a cheap pre-filter deciding whether the expensive check is worth
running. Not built because "clauses that disagree" is itself the hard problem,
and building a detector for it to decide whether to run a detector for it needs
a corpus that does not exist yet.

**Make it a per-question option in the interface.** Rejected: a safety check the
user chooses is a safety check that is off when it matters.
