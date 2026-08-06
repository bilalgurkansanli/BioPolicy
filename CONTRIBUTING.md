# Contributing

This is a portfolio project, not a product with a roadmap. That does not make
contributions unwelcome — it just means the bar for a change is "does this make
the thing more correct, or more honest about itself", rather than "is it on the
plan".

The most useful thing you can send is a **question the system answers wrongly**.
Refusal behaviour is the whole claim here, and every counter-example is worth
more than a feature.

## Getting it running

Two services and a database. The [README](./README.md#running-it-locally) has
the full sequence; the short version:

```bash
uv sync --extra dev                     # Python 3.12
cp .env.example .env                    # then fill in the keys you have
uv run uvicorn api.main:app --reload    # API on :8000

cd web && npm ci && npm run dev         # web on :3000
```

Without provider keys the API still boots and `/api/health` says which
capability is missing rather than failing opaquely — that is deliberate
([ADR 001](./docs/adr/001-config-strictness-by-environment.md)). You can read
the code, run the tests and work on the interface with no credentials at all.

## What CI will check

Everything below runs on every pull request, and all of it runs locally:

```bash
uv run ruff check api eval && uv run ruff format --check api eval
uv run mypy api eval
uv run pytest api/tests -q -m "not integration and not eval"

cd web && npm run lint && npx tsc --noEmit && npm test && npm run build
```

Two things are deliberately **not** in CI: the integration tests, which need a
live Supabase, and the evaluation harness, which calls real models and costs
real money. If your change could move the numbers, say so in the pull request
and I will run `python -m eval.run_eval` before merging.

## Conventions

- **Comments explain why, not what.** The code says what it does. A comment
  earns its place by recording the reason a decision went one way — especially
  when the obvious alternative looks better than it is.
- **A decision that shapes the system goes in an ADR.** There are
  [fifteen of them](./docs/adr); `000-template.md` is the shape. Small changes
  do not need one; "we should use X instead of Y" does.
- **Numbers come from the harness.** No figure in the README, the report or the
  interface is typed by hand. If you want to claim an improvement, generate it.
- **Both languages or neither.** Interface copy lives in `web/lib/i18n.ts` and
  report copy in `eval/copy.py`, with Turkish and English adjacent in the same
  object. The English dictionary is typed against the Turkish one, so a missing
  translation is a compile error rather than a screen with `undefined` on it.
- **Commit messages are sentences.** "Let the pointer say what is clickable",
  not "fix css". They are the closest thing this repository has to a changelog.

## Pull requests

Small and single-purpose. Say what changed, why, and what you did to convince
yourself it works — a paragraph of the last one is worth more than a checklist
of the first two.

If a change touches refusal, citations or spending, it needs evidence: a test,
a measurement, or a question the old code got wrong and the new one gets right.
