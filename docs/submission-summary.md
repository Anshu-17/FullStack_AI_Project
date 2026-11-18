# Submission summary - Business Evidence Platform

**What it does.** Upload companies (CSV or one URL); a background worker crawls each public website safely, an AI
classifies seven business lines (Accounting, Agronomy, Grain, Energy, Feed, Gas Station, Retail Store) and every
website-derived Yes / Possible is backed by a **verbatim quote the system verifies against the crawled page**.
Reviewers correct answers (the human answer wins, with full history and conflict flags) and export CSV / JSON.

**Stack.** Python 3.13 · FastAPI · PostgreSQL (Supabase) · SQLAlchemy + Alembic · Postgres-based job queue with
leases · httpx + BeautifulSoup crawler · Gemini (primary) + Groq (fallback) · Streamlit · Docker on Render.

## Status matrix (full version: [status-matrix.md](status-matrix.md))

| Built and proven | Built but unverified | Partial | Not built |
|---|---|---|---|
| CSV / URL intake with row-level results (1,000 rows ~1.4 s); dedup by domain; safe crawler (SSRF, robots, budgets); evidence-validated classification with Accounting rule; Possible / Not Found semantics; provider retries + fallback; worker leases, crash recovery, cancel, manual retry; idempotent runs; corrections with optimistic locking and audit trail; human-wins answers with conflict flags; search, filters, export; login + roles; rate limits; structured logs, health / readiness, metrics; reversible migrations; **scenarios A-E demonstrated, F-J tested / demonstrated**; 15-site real pilot + manual audit; 100-job synthetic workload; **live deployment on Render + Supabase (smoke-tested 2026-11-18)**; responsive layout (checked at 390 px); login kept across refresh; [Loom walkthrough](https://www.loom.com/share/9a1d51cb8e4e41a08729343b01b293ea) | keyboard use (Streamlit defaults, no audit) | evidence relevance (audit: 66 OK / 9 weak / 3 questionable of 78 quotes); contradictory sources (prompt rule only); AI cost (tokens recorded, cost unknown on free tiers); DNS-rebinding defence (no IP pinning); multi-worker execution (one process run); AI usage statement (draft) | JavaScript-rendered sites; multi-tenancy; real CRM integration (mapping proposed only); user-management screens |

## Key numbers (all from real runs - [evidence/README.md](evidence/README.md))

- **Real-site pilot:** the 12 suggested + 3 added companies; 12 classified, 3 failed (2x HTTP 403, 1 TLS chain - sites
  not bypassed). Audit of 78 quotes: 66 OK, 9 weak, 3 questionable; 2 clear false negatives (Groq fallback).
- **Fixture evaluation (9 synthetic sites, real Gemini):** 54/54 with prompt p3, **tuned on the same set - fit, not
  real-world accuracy; no held-out set.**
- **Synthetic workload (fixtures + fake AI, 2 threads):** 100 jobs ~70 jobs/min, p50 0.74 s per job, 0 duplicates.
- **Crash recovery:** worker hard-killed mid-job -> lease expired, job finished once, exactly 7 answers.
- **Tests:** 250 backend (88 % line coverage) + 12 frontend, all passing.

## Top risks

1. **Free-tier AI quotas** (Gemini 20 requests/model/day) stall real batches - seen in the pilot.
2. **Free hosting**: API + worker share one sleeping container (~512 MB); jobs only progress while it is awake;
   ~1 minute cold start.
3. **Accuracy on unseen sites is unmeasured** (no held-out labelled set); the Groq fallback is weaker.

## Next three priorities

1. Label 30-50 real companies by hand as a held-out set and measure precision / recall on it.
2. Separate always-on worker service + paid / budgeted AI tier with a shared per-provider rate limiter.
3. Crawl hardening: IP pinning (DNS rebinding), smarter page selection, optional JavaScript-rendering lane.

## Submission message (brief section 15)

1. Frontend: https://bep-ui-1dt0.onrender.com  2. Backend / API: https://bep-api.onrender.com (docs: https://bep-api.onrender.com/docs)
3. Repository: https://github.com/Anshu-17/FullStack_AI_Project  4. Loom: https://www.loom.com/share/9a1d51cb8e4e41a08729343b01b293ea
5. Documentation: `README.md` + `docs/`  6. Test / run evidence: `docs/evidence/README.md`
7. Status matrix: this page + `docs/status-matrix.md`
Credentials (`reviewer@demo.local`, `viewer@demo.local`): sent separately **[via the evaluator-approved method]**,
never in the repository or the video. Free hosting sleeps when idle: the first load can take ~1 minute.
