# Scenario C - duplicates (same company, same request, double-click)

**Question:** can the same company, run or result be created twice - by adding a company again, by
double-clicking "start run", or by starting two runs for one company?
**Answer shown here:** no. Each case is blocked by a database rule, not only by application code.

Date: 2026-11-18 (all times UTC). API at http://localhost:8000, database `bep` (PostgreSQL 18).

## Rules and where they are enforced

| Duplicate | Rule | Enforced by |
|---|---|---|
| Same company twice | one company per canonical domain (`https://WWW.Agtegra.com/about` = `agtegra.com`) | UNIQUE `companies.canonical_domain` + `INSERT ... ON CONFLICT DO NOTHING` |
| Same run twice (retry / double-click) | same `Idempotency-Key` returns the same run | UNIQUE `runs.idempotency_key` |
| Same company twice in one request | ids collapse to one job | code + UNIQUE `jobs (run_id, company_id)` |
| Same company in two runs at once | skipped as `already_in_progress` | partial UNIQUE index: one queued/running job per company |
| Same result twice for a job | one answer per category per job; finalize only by the lease owner | UNIQUE `classifications (job_id, category)` + lease fencing |

## Steps and observed results

### 1. Add companies (one already exists)

```
[07:54:04Z] POST /api/companies https://www.agtegra.com -> HTTP 200
    {"created": false, "company": {"id": 1, "name": "Agtegra Cooperative", "website_url": "https://www.agtegra.com/", "canonical_domain": "agtegra.com", ...}}
[07:54:04Z] POST /api/companies https://www.insightfs.com -> HTTP 201
    {"created": true, "company": {"id": 3, "name": "Insight FS", "website_url": "https://www.insightfs.com/", "canonical_domain": "insightfs.com", ...}}
```
Expected: Agtegra already existed (added earlier) -> 200 and the existing id, no new row. Observed: as expected.
(Company id 2 is unused: the conflicting INSERT for Agtegra consumed a sequence number - harmless.)

### 2. Start a run twice with the same Idempotency-Key (and a duplicated id)

Body `{"company_ids": [1, 3, 1]}`, header `Idempotency-Key: scenario-c-demo-1`, sent twice:
```
[07:54:18Z] POST /api/runs (Idempotency-Key: scenario-c-demo-1) call #1 -> HTTP 201
    {"run_id": 6, "status": "queued", "total_items": 2, "skipped": [], "created": true}
[07:54:18Z] POST /api/runs (Idempotency-Key: scenario-c-demo-1) call #2 -> HTTP 200
    {"run_id": 6, "status": "queued", "total_items": 2, "skipped": [], "created": false}
```
Expected: one run; second call returns it with 200; company 1 listed twice -> one job. Observed: as expected.

### 3. Start another run for a company that is already queued (different key)

```
POST /api/runs company 1, different key -> HTTP 409
    {"error": {"code": "NOTHING_TO_RUN", "message": "None of the requested companies can be started.", "details": {"skipped": [{"company_id": 1, "reason": "already_in_progress"}]}}}
```

### 4. Database proof

```
runs with key scenario-c-demo-1: 1 | jobs in run 6: [(6, 1, 'queued'), (7, 3, 'queued')] | active jobs for company 1: 1
```
After the worker finished run 6:
```
run 6: status=completed key=scenario-c-demo-1 started=07:54:40Z finished=07:55:24Z total_items=2
job 6: classifications=7 distinct categories=7
job 7: classifications=7 distinct categories=7
active jobs per company (must be <= 1): []
```

Run progress while one worker (2 threads) processed run 6 (`GET /api/runs/6`, polled every 2 s):
```
[07:54:42Z] run 6 running    progress 0/2 | Agtegra Cooperative: running (attempt 1), Insight FS: running (attempt 1)
[07:55:10Z] run 6 running    progress 1/2 | Agtegra Cooperative: running (attempt 1), Insight FS: review_required (attempt 1)
[07:55:24Z] run 6 completed  progress 2/2 | Agtegra Cooperative: review_required (attempt 1), Insight FS: review_required (attempt 1)
```

## Result: PASS

## Also covered by automated tests

- `tests/test_runs.py`: same key -> same run (1 run, 1 job in the DB); duplicate ids collapse; unknown ids skipped;
  active company skipped / 409 `NOTHING_TO_RUN`.
- `tests/test_ingest.py`: duplicate website in one CSV -> `duplicate` with the row it repeats; existing company ->
  `existing`; **two threads ingesting the same domain at the same instant -> exactly one company, no error**.
- `tests/test_db_integrity.py`: the database itself rejects a second company with the same domain, a second job
  for a company in one run, a second answer for a category in one job, a reused idempotency key.
- `tests/test_worker.py`: two workers claiming concurrently never get the same job; a worker that lost its lease
  saves nothing.
