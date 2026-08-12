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
| `gemini-3.6-flash` pricing | **$1.50 / $7.50** per million input / output tokens | 2026-08-09 |
| Embedding model **in force** | `voyage-4-lite` ([ADR 016](./adr/016-voyage-embeddings.md)) | 2026-08-12 |
| Embedding fallback model | `gemini-embedding-001` — used only when `VOYAGE_API_KEY` is unset | 2026-08-12 |
| Embedding dimensions requested | **1024, confirmed by a live call** — `output_dimension: 1024`, and `validate_dimensions` refuses any other width | 2026-08-12 |
| `voyage-4-lite` pricing | **$0.02** per million tokens, after a one-off 200M free allowance | 2026-08-10 |
| `gemini-embedding-001` pricing | **$0.15** per million input tokens (no output tokens) — the fallback's rate | 2026-08-09 |
| `turkish` FTS config present in Postgres | **yes** — `fts_tr` built with `'turkish'::regconfig`, not the `simple` fallback | 2026-08-04 |
| HNSW index on `vector(1024)` | `chunks_embedding_idx` present and valid after migration 0012 — C3 holds end to end | 2026-08-12 |

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
   measures the returned vector against `EMBEDDING_DIM` (1024). Until this
   passes, the storage design rests on a documented assumption rather than a
   fact. **Do not run migrations or ingest anything until it does.**

   **It probes the fallback, not the embedder in force.** The script calls
   `gemini-embedding-001` directly; since ADR 016 the provider actually used is
   `voyage-4-lite` whenever `VOYAGE_API_KEY` is set. So a green run proves the
   column width is achievable, not that the configured embedder honours it. What
   proves that is the first ingest: `VoyageEmbedder` asks for
   `output_dimension: 1024` and `validate_dimensions` raises on anything else,
   before a single row is written. Confirm which provider a running process
   chose with `/api/health` — `retrieval.embedding_model` is the answer, and it
   is read from the same `build_embedder` the pipeline uses.

A full run costs a fraction of a cent. Record the chosen model IDs and today's
date in the table above.

### Gemini pricing

Not hardcoded, by design — the same do-not-fabricate rule that governs model IDs
governs prices. They arrive as configuration, with the date they were checked:

```bash
MODEL_PRICES=gemini-embedding-001:0.15:0,gemini-3.6-flash:1.50:7.50
MODEL_PRICES_VERIFIED_ON=2026-08-09
```

`model:input:output`, USD per million tokens. `MODEL_PRICES_VERIFIED_ON` is
mandatory whenever a price is set — a rate nobody can date is a rate nobody
checked.

**Why this is not cosmetic.** Until these were set, every Gemini call was
recorded at zero: not free, *invisible to the circuit breaker*. Measured on the
real configuration, a 30-page OCR document costs **$0.24** — as much as this
project had spent in total up to that point — and none of it moved the number
`GLOBAL_BUDGET_USD` is watching. OCR dominates cost precisely because it bills
per page image, so the cheapest path to blowing the ceiling was the one the
accounting could not see.

The consequences of leaving them unset are now graded by environment:

| `APP_ENV` | behaviour |
|---|---|
| `development` | `/api/health` returns `degraded` and lists the models under `unpriced` |
| `preview`, `production` | **refuses to boot**, naming the models |

Re-check the figures whenever a model id changes, and update both the table
above and the date. A stale price is a silent under-count, which is the same
failure in a slower form.

### Voyage rate limits are a deployment variable, and they set ingest time

Voyage meters **both** requests and tokens per minute, and an account with no
payment method on file is held at **3 RPM / 10K TPM** — which it says outright
when it throttles. `config.py` defaults to exactly that, because it is what a
fresh account gets and pacing faster than the server allows converts progress
into 429s and backoff.

This is the largest single term in how long an ingest takes. A 27-page policy is
~36K tokens, so on the reduced tier 3.6 of its four minutes are this ceiling and
nothing else.

**Lifting it with the provider does nothing on its own.** The limit is enforced
on both sides and the slower one wins, so raising the account's ceiling means
also raising it in the deployment:

```bash
VOYAGE_REQUESTS_PER_MINUTE=2000
VOYAGE_TOKENS_PER_MINUTE=16000000
```

Copy whatever the provider's own Rate Limits page states for the account. What a
running process actually believes is readable without guessing — `/api/health`
reports `retrieval.embed_requests_per_minute` and `embed_tokens_per_minute`, and
those two fields exist because both were once wrong in a live process for an
afternoon with no way to see it from outside.

### Embedding spend does not reach the circuit breaker

Stated here rather than in the backlog, because the section on the breaker below
would otherwise read as a promise the accounting does not keep.

`api/ingest/pipeline.py` embeds a whole document without writing a `usage_events`
row, so `GLOBAL_BUDGET_USD` is watching a total that every ingest is absent from.
Voyage is not in `Settings.priced_models` either, so `/api/health` will not flag
it as `unpriced` — it is invisible in both directions.

Under Gemini the obstacle was real: the endpoint reported
`billable_character_count` against a per-token rate card, and the ratio was a
number this project would not invent. Voyage removed that obstacle —
`usage.total_tokens` is the provider's own figure in the provider's own unit —
and the ledger has not caught up yet. Until it does, **the provider console spend
limits are the only guard on embedding cost.** Never remove them on the grounds
that a budget ceiling exists in the application.

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
with `API_ORIGIN` in `web/.env.local`.

### Before anyone can sign in: enable Google

Google is the only way in ([ADR 013](./adr/013-google-only-sign-in.md)), and the
provider is **off by default** on a new Supabase project. Until it is on,
nobody can ask a question or upload anything; the samples and the evaluation
stay readable.

1. **Google Cloud console** → *APIs & Services* → *Credentials* → create an
   **OAuth client ID** of type *Web application*.
   - Authorised redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback`
2. **Supabase dashboard** → *Authentication* → *Sign In / Providers* → **Google**
   → enable, paste the client ID and secret.
3. Add every origin the app is served from to *Authentication* → *URL
   Configuration* → **Redirect URLs**: `http://localhost:3000/**` for local work
   and the deployed origin. A missing entry fails *after* Google, with the
   visitor bounced back to a blank page — the most confusing possible symptom.

The interface detects a disabled provider specifically and names the setting, so
that failure reads as a sentence rather than a generic sign-in error.

`web/.env.local` also has to exist, holding `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` — see `.env.example`.

### The unlimited account

`UNLIMITED_EMAILS` exempts addresses from the daily limits. It is matched
against `auth.users` at check time — never taken from a token — and only for a
**confirmed Google** account that is not banned, deleted or anonymous. An empty
value grants nothing, which is what an unconfigured deployment gets.

To check what the server thinks of an account:

```sql
select email, email_confirmed_at is not null as confirmed,
       raw_app_meta_data ->> 'provider' as provider, banned_until
  from auth.users where email = 'you@example.com';
```

`provider` must read `google`. If it reads `email`, that row was created by a
password sign-up and will not be exempt no matter what the address says — which
is the intended behaviour, not a bug.

Quality gates, all of which CI also runs:

```bash
uv run ruff check api eval && uv run ruff format --check api eval && uv run mypy api && uv run pytest api/tests -q
```

---

## Deploying

> Not deployed yet, deliberately. This section is the checklist for when it is.

### What `vercel.json` does and does not cover

The repository root carries a `vercel.json` with **security headers for `/api/*`
only**. Everything else about the API deployment is a *project setting*, not a
file:

| Setting | Value | Where |
|---|---|---|
| Framework Preset | **Container** | dashboard |
| Root Directory | `.` | dashboard |
| Region | wherever the Supabase project lives | dashboard |

Three things were **not** written into the file on purpose, because guessing
them is worse than leaving them to the dashboard:

* **`framework`** — the published `vercel.json` reference does not list the
  slug for container deployments, and a wrong slug fails the build with a
  message about a framework rather than about a typo.
* **`regions`** — the right answer is "next to Supabase", which depends on where
  that project was created. The default is `iad1`; a database on another
  continent turns every query into a transatlantic round trip.
* **The Dockerfile name.** The Container preset looks for a `Dockerfile`; ours
  is `Dockerfile.vercel`, from before that preset existed. Either rename it or
  point the project at it — but check which one the existing working
  configuration expects before changing anything.

### Environment variables

Both projects need their own set. The API project takes everything in
`.env.example` **except** the `NEXT_PUBLIC_` block; the web project takes only:

    NEXT_PUBLIC_SUPABASE_URL
    NEXT_PUBLIC_SUPABASE_ANON_KEY
    API_ORIGIN            → the api project's own *.vercel.app hostname
    NEXT_PUBLIC_SITE_URL  → https://biopolicy.bilalgurkansanli.com

`API_ORIGIN` is read at build time by `web/next.config.ts`, so changing it needs
a redeploy of the web project rather than a restart.

**`NEXT_PUBLIC_SITE_URL` is the one with a silent failure mode.** It is the
origin every absolute URL a crawler reads is built from: the canonical link on
each page, every entry in `sitemap.xml`, the `Host` line in `robots.txt`, and
the Open Graph image. Unset, `web/lib/site.ts` falls back to Vercel's
`VERCEL_PROJECT_PRODUCTION_URL`, and that names a domain Vercel picks. When it
picks the `*.vercel.app` one nothing errors — the site simply publishes a
sitemap and a set of canonicals pointing at a second hostname serving identical
pages, which is the standard way to split one domain's ranking across two
addresses. Set it explicitly and the guess never happens.

It is read at build time like `API_ORIGIN`, and by the same mechanism: changing
it in a running deployment does nothing until a rebuild.

### After the first deploy

1. Point `app_settings.api_base_url` at the API hostname, and
   `app_settings.purge_job_secret` at the same value as `PURGE_JOB_SECRET` —
   the scheduled jobs do nothing until both rows exist.
2. Add the deployed origin to Supabase → *Authentication* → *URL Configuration*
   → **Redirect URLs**, or Google sign-in returns to a blank page.
3. Run `python -m api.scripts.seed_samples` against the deployed environment so
   the demo has its three documents.
4. Check `/api/health` reports every provider as `configured`.
5. **Confirm the crawler sees the right hostname**, which is one command and
   catches the `NEXT_PUBLIC_SITE_URL` failure above:

   ```bash
   curl -s https://biopolicy.bilalgurkansanli.com/robots.txt
   ```

   Both `Host:` and `Sitemap:` must name the custom domain. If either says
   `*.vercel.app`, the variable did not reach the build — fix it and redeploy
   before anything gets indexed.
6. Add the property in Google Search Console, paste its token into
   `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` on the web project and redeploy — the
   `<meta name="google-site-verification">` tag is emitted only when that
   variable is set — then submit `/sitemap.xml` from the same screen.

### The topology

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

Both scheduled jobs call back into the API rather than running SQL, so they need
`app_settings` populated:

```sql
insert into app_settings (key, value) values
  ('api_base_url', 'https://your-api-host'),
  ('purge_job_secret', 'the same value as PURGE_JOB_SECRET')
on conflict (key) do update set value = excluded.value, updated_at = now();
```

Until both rows exist the jobs log a warning and do nothing, which is deliberate
— migrations must apply cleanly to an unconfigured project. To check the purge
end to end by hand:

```bash
curl -s -X POST "$API_BASE/api/internal/purge" -H "X-Job-Secret: $PURGE_JOB_SECRET"
```

It answers `{"purged": n, "chunks_deleted": n, "failed": n, "orphans_deleted": n}`.
A non-zero `failed` means the storage object could not be deleted; those rows are
kept deliberately and retried on the next sweep, because a row without its file
is the one state retention must never produce.

### The state the fallback produces, and how to see it

`orphans_deleted` counts the *other* direction: a file with no row. Migration
0007's database-side fallback `purge_expired_rows()` runs hourly, deletes rows
and cannot touch the bucket, so every document it expires leaves its PDF behind.
The migration said the API reconciled those. It did not — that sweep did not
exist until `RetentionService.reconcile_orphans`, and on the development project
the fallback had run 5 times and left **6 PDFs in the bucket, the oldest 5 days
past its deletion date**. They were deleted on 2026-08-09.

Two symptoms distinguish the fallback from a real purge, and both are worth
checking after any outage:

```sql
select storage_deleted, count(*) from retention_audit group by 1;
```

Every `false` is a document whose row went without its file. The API always
writes `true`; only the fallback writes `false`. A column of `false` means the
API purge has never once run — check `app_settings` before anything else.

```sql
select count(*) from storage.objects o
 where o.bucket_id = 'documents' and o.name like 'uploads/%'
   and not exists (select 1 from documents d where d.storage_path = o.name);
```

This must be zero. Anything else is a file outliving the promise printed on the
workspace. Reconciliation now runs inside every purge sweep, so a non-zero count
means the sweep itself is not running.
