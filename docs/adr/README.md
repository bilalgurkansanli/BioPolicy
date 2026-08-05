# Architecture decision records

Why things are the way they are — including the things that did not work.

Each record states the constraint that forced the decision, what was rejected,
and what the decision costs. A record with no cost section has not been written
honestly, and a decision that was never revisited is not the same as one that
was right.

Records are **never edited after acceptance**. When a decision changes, a new
record supersedes the old one and the old one stays, marked. ADR 012 is the
example: anonymous accounts were shipped, then replaced.

| # | Decision | Status |
|---|---|---|
| [001](./001-config-strictness-by-environment.md) | Configuration is strict when deployed, permissive in development | accepted |
| [002](./002-pdf-parsing-stack.md) | PDF parsing on pypdfium2 + pdfplumber — not PyMuPDF, Unstructured or Docling | accepted |
| [003](./003-llamaindex-scope.md) | LlamaIndex is used for node parsing and nothing else | accepted |
| [004](./004-model-ids-are-verified-not-recalled.md) | Model IDs are verified against a live list, never recalled from memory | accepted |
| [005](./005-ocr-page-cap.md) | Vision OCR is capped at 30 pages, enforced before the job starts | accepted |
| [006](./006-deployment-topology.md) | Two Vercel projects behind one origin, joined by a rewrite | accepted |
| [007](./007-ingestion-job-execution.md) | The `documents` table is the queue; pg_cron is the watchdog | accepted |
| [008](./008-chunking-without-markdownnodeparser.md) | Structure is tracked in our own parser output, not re-derived from Markdown | accepted |
| [009](./009-figures-are-never-fuzzy.md) | Citation matching is fuzzy on letters and exact on figures | accepted |
| [010](./010-no-token-streaming.md) | Stage events, not token streaming | accepted |
| [011](./011-locale-is-a-preference.md) | Locale is a preference, not a route | accepted |
| [012](./012-anonymous-accounts.md) | Anonymous accounts, not sign-up | **superseded by 013** |
| [013](./013-google-only-sign-in.md) | Google-only sign-in, and one allowlisted account | accepted |
| [014](./014-entailment-check.md) | The entailment check: built, measured, switched off | accepted |
| [015](./015-hostile-documents.md) | When the document is the attacker | accepted |

## The four worth reading first

If you only read a few, these carry the most of the project's reasoning:

- **[014](./014-entailment-check.md)** — a mechanism built because the evaluation
  asked for it, measured, and then switched off by its own numbers. Includes the
  admission that two mechanisms which also changed no decisions are still on.
- **[015](./015-hostile-documents.md)** — measuring the attack before building
  the defence, a fix that failed, and two metrics that had to be corrected after
  seeing results.
- **[010](./010-no-token-streaming.md)** — choosing the slower-feeling interface
  because the faster one can only retract claims it has already delivered.
- **[002](./002-pdf-parsing-stack.md)** — rejecting the better parser because its
  cost lands on every cold start of a scale-to-zero platform.

New records start from [`000-template.md`](./000-template.md).
