# Runbook

Operational procedures. Written for the version of me that is tired and it is
2am. Keep it blunt.

---

## Verified facts

Things that must not be guessed, with the date they were checked.

| Fact | Value | Verified |
|---|---|---|
| Primary LLM model ID | `claude-haiku-4-5-20251001` | 2026-08-03 |
| Gemini fallback LLM model ID | _not yet verified — see below_ | — |
| Gemini vision OCR model ID | _not yet verified — see below_ | — |
| Embedding model | `gemini-embedding-001` | — |
| Embedding dimensions requested | 1536 (of 3072 native) | 2026-08-03 |
| `turkish` FTS config present in Postgres | _not yet checked_ | — |

### Verifying the Gemini model IDs

Per [ADR 004](./adr/004-model-ids-are-verified-not-recalled.md) these ship empty
rather than guessed. To fill them in, with `GOOGLE_API_KEY` set:

```bash
uv run python -m api.scripts.list_models
```

Record the chosen IDs and today's date in the table above, then set
`GEMINI_FALLBACK_MODEL` and `GEMINI_OCR_MODEL` in every environment.

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
