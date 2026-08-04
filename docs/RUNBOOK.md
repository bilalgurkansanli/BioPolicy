# Runbook

Operational procedures. Written for the version of me that is tired and it is
2am. Keep it blunt.

---

## Verified facts

Things that must not be guessed, with the date they were checked.

| Fact | Value | Verified |
|---|---|---|
| Primary LLM model ID | `claude-haiku-4-5-20251001` (alias: `claude-haiku-4-5`) | 2026-08-04 |
| Haiku 4.5 pricing | **$1.00 / $5.00** per million input / output tokens | 2026-08-04 |
| Haiku 4.5 context / max output | **200K / 64K** — smaller than the Opus tier's 1M/128K | 2026-08-04 |
| Haiku 4.5 rejects `effort` | yes — do not pass `output_config.effort` | 2026-08-04 |
| Haiku 4.5 accepts `temperature` | yes — unlike the newest Opus/Sonnet models | 2026-08-04 |
| Gemini fallback LLM model ID | `gemini-3.6-flash` | 2026-08-04 |
| Gemini vision OCR model ID | `gemini-3.6-flash` | 2026-08-04 |
| Gemini pricing | _not yet verified — configuration, defaults to unpriced_ | — |
| Embedding model | `gemini-embedding-001` | 2026-08-04 |
| Embedding dimensions requested | **1536 confirmed by a live call** (of 3072 native) | 2026-08-04 |
| `turkish` FTS config present in Postgres | **yes** — `fts_tr` built with `'turkish'::regconfig`, not the `simple` fallback | 2026-08-04 |
| HNSW index on `vector(1536)` | built successfully — C3 holds end to end | 2026-08-04 |

### A listed model is not necessarily a callable model

`gemini-2.5-flash` appears in `models.list()` and returns **404 — "no longer
available to new users"** when actually called. Enumerating the model list is
therefore *not* sufficient verification; only a real request is. This is why
`list_models` pings rather than just lists.

`gemini-flash-latest` is deliberately **not** used. It is a moving alias, and
ADR 004's reasoning applies unchanged: a model that can change under you makes
every number in `eval/report.md` non-reproducible. Pin the dated id.

### The first thing to run once keys exist

```bash
uv run python -m api.scripts.list_models
```

This is not just a listing. It:

1. Enumerates Gemini models by capability, so `GEMINI_FALLBACK_MODEL` and
   `GEMINI_OCR_MODEL` can be filled in from a live list rather than guessed
   ([ADR 004](./adr/004-model-ids-are-verified-not-recalled.md)).
2. Pings the Anthropic model with one tiny request.
3. **Tests constraint C3 for real** — makes an actual embedding call and
   measures the returned vector. The entire storage design assumes
   `gemini-embedding-001` honours `output_dimensionality: 1536`. Until this
   passes, that is a documented assumption, not a fact. **Do not run migrations
   or ingest anything until it does.**

A full run costs a fraction of a cent. Record the chosen model IDs and today's
date in the table above.

### Gemini pricing

Not hardcoded, by design — the same do-not-fabricate rule that governs model IDs
governs prices. Register them at startup with a verification date:

```python
from api.pricing import register
register("gemini-embedding-001", input_per_mtok=..., output_per_mtok=..., verified_on="YYYY-MM-DD")
```

Until registered, a Gemini call raises `UnpricedModelError` rather than being
recorded as free. That is deliberate: a zero rate does not make a call free, it
makes it invisible to the circuit breaker.

### Verifying the Turkish text-search configuration

The `chunks.fts_tr` generated column depends on a `turkish` configuration
existing on the Postgres instance. Check before trusting it:

```sql
select cfgname from pg_ts_config order by cfgname;
```

If `turkish` is absent, fall back to `simple` in the migration and write an ADR
saying so. Do not ship a silently broken FTS column — it would degrade Turkish
retrieval with no error anywhere, and the eval would report the damage without
explaining it.

---

## Connecting to Postgres

Two things about `DATABASE_URL` that each cost real debugging time:

**1. Percent-encode the password.** A Postgres password containing `@` `:` `/`
`?` `#` `[` `]` or `%` must be encoded in the URI. Unencoded, the `@` is read as
the userinfo/host separator, the host becomes a fragment of the password, and
the port becomes garbage. asyncpg then fails with
`invalid literal for int() with base 10: 'uF'` — a message that mentions
neither passwords nor URIs. `config.py` now catches this at startup and says so
plainly, but encode it correctly in the first place:

```bash
python -c "import urllib.parse,getpass; print(urllib.parse.quote(getpass.getpass(), safe=''))"
```

**2. The transaction pooler needs `statement_cache_size=0`.** We use Supabase's
transaction pooler (port **6543**), which is the right choice for a
scale-to-zero deployment — short-lived instances, many of them, none holding a
session open. But pgbouncer in transaction mode hands a different backend
connection to each statement, while asyncpg caches server-side prepared
statements by name and assumes they persist. The two disagree *intermittently*,
surfacing as `prepared statement "__asyncpg_stmt_x__" does not exist` on a query
that worked moments earlier. Every `asyncpg.connect` / pool in this project
passes `statement_cache_size=0`.

The session pooler (port 5432) avoids the issue and needs no flag, at the cost
of holding a connection per client — the wrong trade for serverless.

## Applying migrations

```bash
uv run python -m api.scripts.migrate --status
```

```bash
uv run python -m api.scripts.migrate
```

Forward-only, numerically ordered, one transaction each, checksummed. Editing a
migration that has already run is refused rather than silently ignored.

## Local development

```bash
uv sync --extra dev
```

```bash
uv run uvicorn api.main:app --reload --port 8000
```

```bash
cd web && npm run dev
```

The frontend proxies `/api/*` to `http://127.0.0.1:8000` by default; override
with `API_ORIGIN`.

Quality gates, all of which CI also runs:

```bash
uv run ruff check api eval && uv run ruff format --check api eval && uv run mypy api && uv run pytest api/tests -q
```

---

## Deploying

Two Vercel projects from one repository ([ADR 006](./adr/006-deployment-topology.md)):

| Project | Root directory | Build | Domain |
|---|---|---|---|
| `biopolicy-web` | `web/` | Next.js | `biopolicy.bilalgurkansanli.com` |
| `biopolicy-api` | `.` | `Dockerfile.vercel` | its own `*.vercel.app` |

The web project needs `API_ORIGIN` set to the API project's hostname.

### DNS

`biopolicy` as a CNAME to Vercel's target, on Cloudflare, set to **DNS-only
(grey cloud)** — not proxied. Proxying in front of Vercel is a well-known source
of redirect loops and certificate failures on first setup. Confirm the
certificate issues before debugging anything else; a cert problem masquerades as
half a dozen other problems.

### Checking a deploy is real

```bash
curl -s https://biopolicy.bilalgurkansanli.com/api/health | jq
```

`status: "ok"` with no `missing` array. A `degraded` response in production
means an environment variable did not make it into the deployment — but note
that a *deployed* environment refuses to boot at all when a required credential
is missing, so a running-but-degraded production API means an optional
capability (OCR, LLM failover) is unset.

---

## When the budget breaker trips

Symptoms: uploads disabled, banner shown, sample documents still queryable.

1. Check actual spend against the provider consoles, not just `usage_events` —
   application-level accounting can be wrong; the console cannot.
2. If the application over-counted, correct `usage_events` and the breaker
   clears on the next check.
3. If spend is real, decide: raise `GLOBAL_BUDGET_USD`, or leave the demo in
   read-only sample mode. Read-only is a legitimate resting state — the sample
   documents demonstrate everything the eval report claims.
4. **Both console spend limits stay in place regardless.** Application limits
   have bugs; console limits don't. Never disable the outer one because the
   inner one exists.

---

## Rotating keys

In order, or you will take an outage:

1. Create the new key in the provider console. Do not revoke the old one yet.
2. Update the variable in **both** Vercel projects and both Supabase
   environments as applicable.
3. Redeploy. Confirm `/api/health` reports the provider as configured.
4. Send one real request through the affected path.
5. Only now, revoke the old key.

For `SUPABASE_SERVICE_ROLE_KEY`, note that rotating it invalidates every
server-side client immediately — there is no overlap window. Do it during a
quiet period.

`PURGE_JOB_SECRET`: rotate the value in the API environment first, then in the
scheduled job. A mismatch means the purge silently 401s, which means documents
outlive their 24 hours. **Check that a purge ran after rotating**, in the audit
table.

The scheduled jobs read their configuration from the `app_settings` table, not
from the cron command text, so rotating is an `UPDATE` rather than a migration:

```sql
update app_settings set value = 'NEW_SECRET', updated_at = now() where key = 'purge_job_secret';
```

Both rows must exist before any scheduled job does anything. On a fresh project:

```sql
insert into app_settings (key, value) values
  ('api_base_url', 'https://biopolicy.bilalgurkansanli.com'),
  ('purge_job_secret', 'PASTE_THE_SECRET_HERE');
```

Until they are set, the jobs log a warning and no-op — deliberately, so that
migrations apply cleanly to an unconfigured project. **A silent no-op means the
retention promise is not being kept**, so verify after first deploy:

```sql
select * from retention_audit order by purged_at desc limit 5;
```

---

## Restoring from a failed migration

Migrations are numbered and forward-only.

1. Do not edit an applied migration. Write a new one that corrects it.
2. If a migration failed partway, check whether it ran inside a transaction. DDL
   in Postgres is transactional, so a failed migration usually leaves nothing
   behind — but `create index concurrently` cannot run in a transaction and can
   leave an invalid index. Find them with:

   ```sql
   select indexrelid::regclass from pg_index where not indisvalid;
   ```

   Drop and recreate.
3. Preview and production are **separate Supabase projects**. Confirm which one
   you are connected to before running anything. The preview project may be
   dropped and rebuilt freely; production may not.

---

## Retention did not run

The 24-hour deletion promise is printed in the UI in two languages. If it fails,
that is a broken promise, not a bug backlog item.

1. Check the audit table for the last successful purge.
2. Check the scheduled job is still scheduled: `select * from cron.job;`
3. Verify `PURGE_JOB_SECRET` matches between the job and the API.
4. Run a purge manually and confirm both the storage object **and** the chunk
   rows disappear. Deleting a row in `storage.objects` does not necessarily
   remove the underlying file — that is why the purge goes through the Storage
   API rather than raw SQL.
5. If documents outlived their window, that is worth a note in the README's
   honesty section. This project does not get to hide its own failures.
