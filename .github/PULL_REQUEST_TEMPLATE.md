<!--
  Delete whatever does not apply. A short pull request with two honest
  sentences beats a long one with a filled-in checklist.
-->

## What this changes

<!-- One paragraph. What was true before, what is true now. -->

## Why

<!--
  The reason, not the restatement. If the obvious alternative looks better than
  what you did, this is the place to say why it isn't.
-->

## How you know it works

<!--
  A test, a measurement, or what you did by hand and what you saw. "The types
  pass" is not evidence that the behaviour is right.
-->

---

- [ ] `ruff`, `mypy` and `pytest` pass locally (`api`, `eval`)
- [ ] `npm run lint`, `tsc --noEmit`, `npm test` and `npm run build` pass (`web`)
- [ ] Interface or report copy changed in **both** languages
- [ ] A decision that shapes the system has an [ADR](../docs/adr)
- [ ] This could move the evaluation numbers — say so, and they will be re-run
      before merge (`python -m eval.run_eval` costs real money, so it is not in CI)
