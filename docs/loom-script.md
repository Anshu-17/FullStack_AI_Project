# Loom recording script (20-30 minutes, brief section 11 agenda)

The brief requires real activity (not slides or pre-recorded output), reproducible with the submitted code, and
scenarios A-E demonstrated. Never show passwords, `.env` or API keys on screen.

**Before recording:** wake the deployed services (open the UI and `/health` ~2 minutes before). Locally, open 4
PowerShell terminals in the repo root:

| Terminal | Command |
|---|---|
| 1 - API | `cd backend; .venv\Scripts\activate; uvicorn app.main:app --port 8000` |
| 2 - UI | `cd frontend; .venv\Scripts\activate; streamlit run app.py` |
| 3 - fixture sites (for D) | `backend\.venv\Scripts\python fixtures\server.py` |
| 4 - worker | `cd backend; .venv\Scripts\activate; $env:JOB_LEASE_SECONDS=30; python -m app.worker.main` |

## 00:00-03:00 - Problem, assumptions, priorities, planned architecture

- The problem: which of 7 business lines does each company operate, and can every answer be proven from its website?
- Assumptions: public websites only; Not Found = "not found within the crawl scope"; Accounting = Yes by policy rule.
- Priorities: a reliable vertical slice (evidence integrity, resilience) over breadth; honest gaps
  (`docs/status-matrix.md`).
- Architecture in one sentence: Streamlit -> FastAPI -> Postgres <- worker (crawler + AI), Postgres is the queue.

## 03:00-07:00 - Codebase, schema, pipeline, interaction diagram (`docs/design.md`)

- Folders: `backend/app/{api,services,crawler,classifier,worker,db}`, `frontend/`, `fixtures/`, `docs/evidence/`.
- Component + sequence diagrams; ERD and the unique constraints that make duplicates impossible.
- Pipeline: crawl -> select passages -> prompt (untrusted tags) -> validate (verbatim quotes) -> Accounting rule ->
  fenced save. Job state machine: retries, lease recovery, cancel.

## 07:00-15:00 - Live demo (deployed app https://bep-ui-1dt0.onrender.com)

1. Log in as reviewer. **Upload** `sample-data/real_companies.csv` (or add one URL) -> accepted / existing /
   duplicate / invalid rows with reasons.
2. **Real analysis:** start research for 1-2 companies -> Runs page, per-item statuses and progress from the server.
3. **Evidence verification:** company detail -> a Yes answer -> verbatim quote, source URL (open it and find the
   sentence on the live site), model / prompt / policy version, "Website" vs "Rule" (Accounting) badges.
4. **Review / override (scenario E):** correct Grain to "Possible" with a reason -> provenance "Human", history table.
5. **Repeat scan:** rescan the company -> final answer stays "Possible" (Human) with
   "⚠ Conflicts with the latest automated scan".
6. **Search and export:** filter Companies by category / status; Export CSV -> `grain_source = human`,
   `grain_conflict = yes`; corrections audit export.
7. **Duplicates (scenario C):** add `https://WWW.Agtegra.com/about` again -> "already existed"; click Start twice ->
   same run (Idempotency-Key). Evidence: `scenario_C_duplicates.md`.

## 15:00-21:00 - Tests, negative cases, logs, retries, restart recovery, auth, URL safety (local)

**A - worker crash mid-batch (2 min)** - start a rescan; when the job is `running`, kill the worker (any terminal):
```powershell
Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'app\.worker\.main' } | % { taskkill /F /T /PID $_.ProcessId }
```
Show the job still `running` with its lease; restart terminal 4's command. After ~30 s: attempt 1 `abandoned`,
attempt 2 `succeeded`, exactly 7 answers. Show the JSON log lines (`job.lease_recovered`). Evidence:
`scenario_A_worker_crash.md`.

**B - AI provider timeout / rate limit / malformed output (1.5 min)**
```powershell
$env:GOOGLE_MODEL='does-not-exist'; python -m app.classifier.cli https://www.agtegra.com --name "Agtegra Cooperative" --quiet
pytest tests/test_classify_pipeline.py tests/test_classifier.py -k "timeout or rate_limit or missing_category or cut_off or daily_quota or all_providers_fail or error_classification"
```
Google `AI_ERROR` once (not retried), Groq `ok`; tests: timeouts / 429 retried with a ceiling, invalid output never
saved, all providers down -> no classifications, job `failed` `AI_UNAVAILABLE`. Evidence: `scenario_B_ai_failures.md`.

**D - malicious site: redirect to private IP + prompt injection (1.5 min)** - stop the worker, restart it with
TEST-ONLY fixture settings:
```powershell
$env:CRAWL_FIXTURE_SERVER='127.0.0.1:8765'; $env:CRAWL_ALLOWED_PRIVATE_HOSTS='*.fixture.test'; python -m app.worker.main
```
Add and run `http://redirect-to-private.fixture.test/` -> `BLOCKED_UNSAFE` (10.0.0.5 never fetched) and
`http://prompt-injection.fixture.test/` -> only Agronomy = yes; the hidden instruction is just page text. Evidence:
`scenario_D_ssrf_and_injection.md`.

**Tests and auth (1 min)** - `cd backend; pytest -q` (250 passed); viewer login -> no edit buttons, API answers 403.

**F-J (30 s)** - name each and its evidence file: F transient DB failure during a write, G concurrent reviewer
edits, H weak / ambiguous / unavailable evidence, I cancellation during a run, J migration with rollback
(`docs/evidence/README.md`).

**Found on the live site -> fixed -> re-verified (1.5 min)** - `docs/evidence/crawl_coverage_improvement.md`:
1. *Found:* on the live site Agfinity showed Gas Station "Not found" although it runs C-Stores and an Ace
   Hardware. Show the BEFORE page list: homepage + 7 agronomy pages - the 8 slots were used up by one section.
2. *Fixed:* `backend/app/crawler/sitemap.py` (sitemap, same SSRF-checked fetch) and `choose_next` in
   `crawler/crawl.py` (one page per category group first, then score minus 3 per page from the same folder).
3. *Re-verified:* `python -m app.crawler.cli https://www.agfinityinc.com --quiet` shows the WHY CHOSEN column
   (no AI needed); then rescan Agfinity on the live site -> Gas Station "24-hour pay-at-pump fueling", Retail
   "Our Brighton Ace Hardware ...". Mention the honest leftovers (energy from menu text).

## 21:00-25:00 - AI tool usage, important generated code, mistakes found, verification (`docs/ai-usage.md`)

- Tools: Claude (chat) for planning / briefs, Claude Code for implementation and tests; Gemini / Groq only inside the
  product. **[Say in your own words what you decided and checked.]**
- Walk through key generated code: `crawler/safety.py`, `classifier/validate.py`, `worker/leases.py`,
  `worker/process.py` (fenced finalize).
- Mistakes found: extract line-break bug (caught by a test), stitched / invented quotes (caught by validation), the
  300-character schema limit rejecting whole answers, p2 -> p3 tuned on the same fixtures (caveat), LangGraph dropped.

## 25:00-30:00 - Performance / cost, unfinished features, trade-offs, hardening

- Numbers: 1,000-row intake ~1.4 s; 100 synthetic jobs ~70/min (fake AI, local fixtures); pilot 12 of 15 classified;
  audit 66 / 9 / 3 of 78 quotes; fixture score 54/54 tuned on the same set. Cost: tokens recorded, price unknown
  (free tier) - not estimated.
- Unfinished: JS-rendered sites, multi-tenancy, CRM sync, multi-worker deployment, IP pinning, held-out set.
- Trade-offs: Postgres as queue; no headless browser; strict verbatim evidence.
- Hardening: separate worker service, paid AI tier + shared rate limiter, retention job, labelled real-world set.
