# Scenario A - worker crash during a job

**Question:** if the worker process dies in the middle of a job, is the job lost, stuck, or finished twice?
**Answer shown here:** none of those. The lease expires, another worker loop recovers the job, the
crashed attempt is recorded as `abandoned`, the job finishes once, with exactly 7 classifications.

Date: 2026-11-18 (all times UTC). Machine: Windows 11, PostgreSQL 18, one API + one worker process.

## Setup

- API: `uvicorn app.main:app --port 8000`
- Worker: `python -m app.worker.main` with `JOB_LEASE_SECONDS=30` set **in that command's environment only**
  (`.env` untouched; the default is 120 s). Heartbeat = every lease/3 = 10 s.
- Real website and real AI: agtegra.com, Gemini `gemini-2.5-flash`.

## Steps

| # | Time | Action |
|---|---|---|
| 1 | 07:55:58 | `POST /api/companies/1/rescan` (Idempotency-Key `scenario-a-crash-1`) -> run **7**, job **8** |
| 2 | 07:55:58 | worker thread `DESKTOP-N3ELC32:24332:t1` claims job 8 (attempt 1) and crawls |
| 3 | 07:56:19 | job 8 is `running` and its 8 pages are saved -> the AI call is in progress |
| 4 | 07:56:23 | **hard kill**: `taskkill /F /T /PID <worker pid>` (whole process tree; no shutdown code runs) |
| 5 | 07:56:26 | DB inspected: job still `running`, lease owned by the dead worker |
| 6 | 07:56:42 | a new worker process is started (`DESKTOP-N3ELC32:14132`) |
| 7 | 07:56:49 | lease expired (07:56:48) -> recovered, re-queued, reclaimed as attempt 2 |
| 8 | 07:57:09 | job 8 finished `review_required`, run 7 `completed` |

## Expected

- After the kill the job stays `running` until its lease (30 s after the last heartbeat) expires - nobody can
  steal it earlier.
- Recovery marks attempt 1 `abandoned` (`WORKER_LOST`) and re-queues the job (attempts remain: 1 of 3 used).
- The retry does not crawl again (pages from attempt 1 are reused) and finishes the job once.
- Exactly 7 classifications for job 8 (unique per job + category; finalize is fenced by the lease).

## Observed - database right after the kill (step 5)

```
[07:56:26Z] DB now=07:56:26Z | job 8: status=running attempt_count=1/3 lease_owner=DESKTOP-N3ELC32:24332:t1 lease_expires_at=07:56:48Z heartbeat_at=07:56:18Z last_error=None
    attempt 1: running    worker=DESKTOP-N3ELC32:24332:t1 error=None started=07:55:58Z finished=None
    event 07:55:58Z None -> queued: created in run 7
    event 07:55:58Z queued -> running: claimed (attempt 1)
    pages saved: 8 | classifications: 0 -> []
```
`worker processes still alive: 0` (checked with `Get-CimInstance Win32_Process` after the kill).

## Observed - run progress while the new worker recovers it (`GET /api/runs/7`, polled every 2 s)

```
[07:56:45Z] run 7 running    progress 0/1 | Agtegra Cooperative: running (attempt 1)   <- dead owner, lease not expired yet
[07:56:51Z] run 7 running    progress 0/1 | Agtegra Cooperative: running (attempt 2)   <- recovered and reclaimed
[07:57:11Z] run 7 completed  progress 1/1 | Agtegra Cooperative: review_required (attempt 2)
```

## Observed - database after recovery

```
[07:57:13Z] DB now=07:57:13Z | job 8: status=review_required attempt_count=2/3 lease_owner=None lease_expires_at=None heartbeat_at=07:57:09Z last_error=None
    attempt 1: abandoned  worker=DESKTOP-N3ELC32:24332:t1 error=WORKER_LOST started=07:55:58Z finished=07:56:49Z
    attempt 2: succeeded  worker=DESKTOP-N3ELC32:14132:t2 error=None started=07:56:49Z finished=07:57:09Z
    event 07:55:58Z None -> queued: created in run 7
    event 07:55:58Z queued -> running: claimed (attempt 1)
    event 07:56:49Z running -> queued: lease of DESKTOP-N3ELC32:24332:t1 expired; re-queued (attempt 1 abandoned)
    event 07:56:49Z queued -> running: claimed (attempt 2)
    event 07:57:09Z running -> review_required: classified with google; statuses {...}
    pages saved: 8 | classifications: 7 -> ['agronomy=yes', 'grain=not_found', 'energy=yes', 'feed=yes', 'gas_station=yes', 'retail_store=yes', 'accounting=yes']
```

Extra checks:
```
run 7: status=completed key=scenario-a-crash-1 started=07:55:58Z finished=07:57:09Z total_items=1
job 8: classifications=7 distinct categories=7
    ai_usage #12 google gemini-2.5-flash outcome=ok tokens=4271/3394 latency=14302ms
```

## Observed - worker log excerpts (JSON, one line per event)

New worker:
```
{"worker": "DESKTOP-N3ELC32:14132", "threads": 2, "lease_seconds": 30, "event": "worker.started", "timestamp": "2026-11-18T07:56:43.548088Z"}
{"job_id": 8, "run_id": 7, "lost_owner": "DESKTOP-N3ELC32:24332:t1", "new_status": "queued", "attempt": 1, "event": "job.lease_recovered", "worker_id": "DESKTOP-N3ELC32:14132:t2", "level": "warning", "timestamp": "2026-11-18T07:56:49.714649Z"}
{"job_id": 8, "run_id": 7, "worker_id": "DESKTOP-N3ELC32:14132:t2", "event": "job.claimed", "timestamp": "2026-11-18T07:56:49.779278Z"}
{"reason": "ok pages saved by an earlier attempt; not crawling again", "event": "job.reusing_pages", "run_id": 7, "attempt": 2, "job_id": 8, "worker_id": "DESKTOP-N3ELC32:14132:t2", "timestamp": "2026-11-18T07:56:49.804384Z"}
{"provider": "google", "model": "gemini-2.5-flash", "input_tokens": 4271, "output_tokens": 3394, "latency_ms": 14302, "event": "ai.call_ok", "run_id": 7, "attempt": 2, "job_id": 8, "worker_id": "DESKTOP-N3ELC32:14132:t2", "timestamp": "2026-11-18T07:57:09.813477Z"}
{"status": "review_required", "reason": "classified with google; ...", "event": "job.finished", "run_id": 7, "attempt": 2, "job_id": 8, "worker_id": "DESKTOP-N3ELC32:14132:t2", "timestamp": "2026-11-18T07:57:09.890347Z"}
```

## Result: PASS

| Check | Result |
|---|---|
| Job stayed `running` with the dead worker's lease until expiry | yes (expires 07:56:48, recovered 07:56:49) |
| Attempt 1 recorded as `abandoned` / `WORKER_LOST` | yes |
| Job re-queued and finished by another worker | yes (attempt 2, `succeeded`) |
| Saved pages reused, no second crawl | yes (`job.reusing_pages`) |
| Exactly 7 classifications, one per category | yes (7 rows, 7 distinct categories) |
| Run status computed from the jobs | `completed`, finished_at set |

## Notes / limitations seen in this run

- The Gemini call that was in flight when the worker was killed has **no `ai_usage` row** (the process died
  before writing it). Its tokens are not counted - a known blind spot of recording usage after the call.
- Grain came back `not_found` this time while earlier scans of the same site said `yes`: Gemini at
  temperature 0 still varies, and its grain quotes in this answer could not be verified, so validation
  demoted them. The job is `review_required`, i.e. flagged for a human.
- Also covered by automated tests (`tests/test_worker.py`): expired lease -> re-queue; expired lease with no
  attempts left -> `failed` / `WORKER_LOST`; a worker whose lease was taken over saves nothing (`LEASE_LOST`).
