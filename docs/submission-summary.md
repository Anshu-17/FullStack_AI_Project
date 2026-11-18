# Submission summary - Business Evidence Platform

**What it does.** Upload a list of companies (CSV or one by one); a background worker crawls each company's public
website safely, an AI classifies seven business lines (Accounting, Agronomy, Grain, Energy, Feed, Gas Station,
Retail Store) and every "yes" must be backed by a **verbatim quote** from a crawled page. Reviewers see the evidence,
correct answers (the human answer wins, with full history), and export CSV / JSON.

**Live:** UI **[UI URL - fill in after deployment]** · API **[API URL]** · API docs **[API URL]/docs**
**Log in:** `reviewer@demo.local` (can change data) or `viewer@demo.local` (read / export) - passwords are shared
privately. **[Note: free hosting sleeps when idle - the first page load can take ~1 minute.]**
**Code:** https://github.com/Anshu-17/FullStack_AI_Project

**Stack.** Python 3.13 · FastAPI · PostgreSQL (Supabase) · SQLAlchemy + Alembic · background worker with
Postgres-based leases · httpx + BeautifulSoup crawler · Gemini (primary) + Groq (fallback) via LangChain ·
Streamlit UI · Docker on Render.

## Built vs not built

| Built and demonstrated | Partial | Not built |
|---|---|---|
| CSV intake with row-level results; dedup by domain; safe crawler (SSRF, robots, limits); evidence-validated classification; provider fallback; worker leases / retries / crash recovery / cancel; idempotent runs; corrections with optimistic locking; human-wins answers with conflict flags; export; login + roles; rate limits; metrics; reversible migrations; scenarios A-J | real-world accuracy (15-site pilot, manual audit, no held-out set); distributed workers (designed, not run); deployment (files ready, not deployed **[update after deploying]**); cost tracking (cost unknown on free tiers); DNS-rebinding protection | JavaScript-rendered sites; multi-tenancy; CRM integration; user management screens |

Full matrix: [status-matrix.md](status-matrix.md).

## Key numbers (all from real runs - see `docs/evidence/`)

- **Real-site pilot, 15 companies:** 12 classified (3 completed, 9 for review), 3 failed because the sites refuse
  crawlers (2x HTTP 403, 1 TLS chain). Manual audit of 78 quotes: 66 OK, 9 weak, 3 questionable; 2 clear false
  negatives (Groq fallback).
- **Fixture evaluation (9 synthetic sites, real Gemini):** 54/54 with prompt p3 - tuned on the same set, so a fit to
  our fixtures, **not** real-world accuracy.
- **Intake:** 1,000-row CSV in one request in ~1.4 s (900 accepted / 50 duplicate / 50 invalid, each with a reason).
- **Synthetic workload:** 100 jobs (local fixtures + fake AI) at ~70 jobs/min on 2 threads, p50 0.74 s per job,
  exactly 7 answers per successful job, 0 duplicates.
- **Crash recovery:** worker hard-killed mid-job -> lease expired, job finished once by another worker, exactly 7
  answers (scenario A).
- **Tests:** 250 backend + 12 frontend, all passing; `ruff` and `alembic check` clean.

## Where to look

| What | File |
|---|---|
| Architecture, diagrams, decisions, scale path | [design.md](design.md) |
| API reference | [api.md](api.md), live `/docs` |
| Evidence for every scenario and number | [evidence/README.md](evidence/README.md) |
| Chronological decisions | [decision-log.md](decision-log.md) |
| How AI was used | [ai-usage.md](ai-usage.md) |
| Limitations and next steps | [limitations.md](limitations.md) |
| Privacy | [privacy.md](privacy.md) |
| CRM mapping (proposal) | [crm-mapping.md](crm-mapping.md) |
| Deployment guide | [deployment.md](deployment.md) |
| Video **[LOOM URL]** | outline: [loom-script.md](loom-script.md) |
