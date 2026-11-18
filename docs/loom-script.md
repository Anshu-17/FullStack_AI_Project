# Loom recording script (20-25 minutes)

Before recording: wake the deployed services (open the UI and `/health` ~2 minutes before), log in once as reviewer.
For the local demos, open 4 terminals in the repo (Windows PowerShell shown; macOS/Linux: `source .venv/bin/activate`
and `export VAR=value`). Have `docs/evidence/` open in a browser tab.

## 0:00-2:00 - Problem and what it does

- The problem: a list of agricultural companies; which business lines does each one have, and can we prove it?
- Show the live UI **[UI URL]**: dashboard (metrics), Companies list (7 answers per company, "Test data" badge),
  one company detail: answer + verbatim quote + source link + model/prompt/policy version.

## 2:00-5:00 - Live end-to-end on the deployed app

1. Log in as reviewer -> **Add companies** -> one website (e.g. `Agtegra Cooperative`, `https://www.agtegra.com`).
2. Start research -> **Runs**: progress refreshes every 3 s, from the server.
3. When done: company detail -> Grain / Energy evidence; open a source link.
4. Correct one answer with a reason -> provenance "Human"; show the history table.
5. **Export** CSV -> open it (human answer shows `source = human`).
6. Log in as viewer -> same data, no edit buttons (backend returns 403 anyway).

## 5:00-8:00 - Architecture (docs/design.md)

- System diagram: UI -> API -> Postgres <- worker -> crawler / AI. UI never touches the DB; API never crawls.
- Sequence diagram: upload -> run -> claim -> crawl -> select -> classify -> validate -> fenced save.
- ERD: the unique constraints that make duplicates impossible.
- Job states: retry, lease recovery, cancel.

## 8:00-16:00 - Scenario demos (local)

Terminal 1 - API: `cd backend; .venv\Scripts\activate; uvicorn app.main:app --port 8000`
Terminal 2 - UI: `cd frontend; .venv\Scripts\activate; streamlit run app.py`
Terminal 3 - fixture server (for D): `backend\.venv\Scripts\python fixtures\server.py`

**A - worker crash (2.5 min)**
```powershell
cd backend; .venv\Scripts\activate
$env:JOB_LEASE_SECONDS=30; python -m app.worker.main          # terminal 4
```
Start a rescan of a real company in the UI; when the job is `running`, kill the worker hard:
```powershell
Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'app\.worker\.main' } | % { taskkill /F /T /PID $_.ProcessId }
```
Show the job still `running` with its lease (Runs -> job details). Restart the worker (same command). After ~30 s:
attempt 1 `abandoned`, attempt 2 `succeeded`, exactly 7 answers. Point to `docs/evidence/scenario_A_worker_crash.md`.

**B - AI failure and fallback (1.5 min)**
```powershell
$env:GOOGLE_MODEL='does-not-exist'; python -m app.classifier.cli https://www.agtegra.com --name "Agtegra Cooperative" --quiet
```
Show the AI calls: Google `AI_ERROR` once (not retried), Groq `ok`. Mention the daily-quota breaker (`skipped_quota`).
Evidence: `hour2_classifier.md`, `real_site_pilot.md`.

**C - duplicates (1.5 min)** - in the UI: add `agtegra.com` again -> "already existed"; upload a CSV with the same
site spelled 3 ways -> 1 accepted, duplicates name the row. Start research twice quickly (double-click) -> same run.
Evidence: `scenario_C_duplicates.md`.

**D - SSRF and prompt injection (1.5 min)** - start the worker with the fixture settings (terminal 4, after stopping
the previous worker):
```powershell
$env:CRAWL_FIXTURE_SERVER='127.0.0.1:8765'; $env:CRAWL_ALLOWED_PRIVATE_HOSTS='*.fixture.test'; python -m app.worker.main
```
Add `http://redirect-to-private.fixture.test/` and `http://prompt-injection.fixture.test/`, run both: the first fails
`BLOCKED_UNSAFE` (redirect to 10.0.0.5, never fetched); the second has only Agronomy = yes, the hidden
"IGNORE ALL PREVIOUS INSTRUCTIONS" is just page text. Evidence: `scenario_D_ssrf_and_injection.md`.

**E - human correction vs new scan (1 min)** - correct Grain on a company to "Possible", rescan, show the final
answer still "Possible" (Human) with "⚠ Conflicts with the latest automated scan". Evidence: `scenario_E_override_conflict.md`.

Mention F-J with their evidence files (DB write failure, concurrent edits, ambiguous vs unavailable, cancel,
migration) - `docs/evidence/README.md`.

## 16:00-20:00 - Code tour (key files)

| File | What to show |
|---|---|
| `backend/app/crawler/safety.py` | every resolved IP must be public; re-checked per redirect hop |
| `backend/app/crawler/crawl.py` | priority queue, limits, cross-domain redirect, duplicate-text pages |
| `backend/app/classifier/select.py`, `prompts.py` | passage budget; untrusted tags |
| `backend/app/classifier/validate.py` | verbatim-quote check, relevance, 25-char rule |
| `backend/app/classifier/pipeline.py` | retries, fallback, quota breaker, every call in `ai_usage` |
| `backend/app/worker/leases.py` | `FOR UPDATE SKIP LOCKED`, heartbeat, recovery |
| `backend/app/worker/process.py` | fenced finalize (`lease_owner == me`), backoff |
| `backend/app/services/overrides.py` | optimistic locking + unique rule |
| `backend/app/db/models.py` | the constraints table in design.md |
| `frontend/api_client.py` | the only place the UI calls the backend |

## 20:00-22:30 - Evidence and numbers (docs/submission-summary.md)

Pilot: 12 of 15 classified, 3 sites refuse crawlers; audit 78 quotes (66 OK / 9 weak / 3 questionable, 2 false
negatives). Fixture evaluation 54/54 - say clearly it is fit to our own 9 synthetic sites, no held-out set.
Intake 1,000 rows ~1.4 s. Synthetic 100 jobs ~70/min, 0 duplicates. 250 + 12 tests.

## 22:30-25:00 - Trade-offs and next steps

- Postgres as the queue; no headless browser; strict verbatim evidence (design.md section 9).
- Free-tier limits: Gemini 20 requests/day/model, sleeping free services.
- Next: labelled real-world test set; separate always-on worker; shared rate limiter for several workers; JS
  rendering lane; IP pinning; CRM sync; multi-tenancy (limitations.md).
