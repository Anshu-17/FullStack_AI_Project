# Scenario I - cancelling a run while a job is running

**FIXTURE data + FAKE AI provider** (the deterministic keyword provider `fake-keyword-v1`, so no AI quota is
spent; the cancel logic is the same for any provider). REAL API, worker, crawler and database.
Date: 2026-11-18 (UTC).

**Question:** if a user cancels a run while jobs are queued and one is running, what happens?
**Answer shown here:** queued jobs are cancelled immediately; the running job stops at its next check point and
ends `cancelled` with NO classifications saved; the run goes `cancelling` -> `cancelled` and never `completed`.

Setup: API + ONE worker process with ONE thread (`WORKER_CONCURRENCY=1`, so the other jobs stay queued),
`AI_PROVIDER=fake`, fixture settings as in scenario D (command environment only). The first company,
`slow-site.fixture.test`, links to a deliberately slow page (`/__slow?seconds=8`), so its job is still running
when the cancel arrives.

## Steps

1. `POST /api/uploads` (5 fixture companies, `source=fixture`) and `POST /api/runs` (run 13).
2. Wait until the first job is `running`, wait 2 s, `POST /api/runs/13/cancel`.
3. Poll the run until it is finished; inspect every job; cancel again.

## Observed

```
[08:54:47Z] POST /api/uploads (source=fixture) -> HTTP 201 counts={'total': 5, 'accepted': 5, 'existing': 0, 'duplicate': 0, 'invalid': 0}
[08:54:47Z] POST /api/runs -> HTTP 201 {"run_id": 13, "status": "queued", "total_items": 5, "skipped": [], "created": true}
[08:54:48Z] before cancel: Slowpoke Grain Company: running; Prairie Gold Copy 101: queued; Prairie Gold Copy 102: queued; Prairie Gold Copy 103: queued; Prairie Gold Copy 104: queued
[08:54:50Z] POST /api/runs/13/cancel -> HTTP 200 status=cancelling cancelled_now=4 counts={'running': 1, 'cancelled': 4}
[08:54:50Z] right after cancel: Slowpoke Grain Company: running; Prairie Gold Copy 101: cancelled; Prairie Gold Copy 102: cancelled; Prairie Gold Copy 103: cancelled; Prairie Gold Copy 104: cancelled
[08:54:50Z] run 13 cancelling 4/5 | Slowpoke Grain Company: running (att 1); Prairie Gold Copy 101: cancelled (att 0); Prairie Gold Copy 102: cancelled (att 0); Prairie Gold Copy 103: cancelled (att 0); Prairie Gold Copy 104: cancelled (att 0)
[08:54:58Z] run 13 cancelled 5/5 | Slowpoke Grain Company: cancelled (att 1); Prairie Gold Copy 101: cancelled (att 0); Prairie Gold Copy 102: cancelled (att 0); Prairie Gold Copy 103: cancelled (att 0); Prairie Gold Copy 104: cancelled (att 0)

RUN 13 final: status=cancelled finished_at=2026-11-18T08:54:57.377693+00:00 counts={'cancelled': 5}

--- job 35 Slowpoke Grain Company (http://slow-site.fixture.test/): status=cancelled last_error=CANCELLED msg=None classifications=0
    attempt 1: failed error=CANCELLED 
    page http://slow-site.fixture.test/: outcome=ok http=200
    page http://slow-site.fixture.test/__slow?seconds=8: outcome=ok http=200
    event None -> queued: created in run 13
    event queued -> running: claimed (attempt 1)
    event running -> cancelled: run cancelled; stopped before saving results

--- job 36 Prairie Gold Copy 101 (http://clear-coop-101.fixture.test/): status=cancelled last_error=None msg=None classifications=0
    event None -> queued: created in run 13
    event queued -> cancelled: run cancelled before the job started

--- job 37 Prairie Gold Copy 102 (http://clear-coop-102.fixture.test/): status=cancelled last_error=None msg=None classifications=0
    event None -> queued: created in run 13
    event queued -> cancelled: run cancelled before the job started

--- job 38 Prairie Gold Copy 103 (http://clear-coop-103.fixture.test/): status=cancelled last_error=None msg=None classifications=0
    event None -> queued: created in run 13
    event queued -> cancelled: run cancelled before the job started

--- job 39 Prairie Gold Copy 104 (http://clear-coop-104.fixture.test/): status=cancelled last_error=None msg=None classifications=0
    event None -> queued: created in run 13
    event queued -> cancelled: run cancelled before the job started

[08:54:58Z] cancel again -> HTTP 409 RUN_FINISHED
```

Worker log for the running job (JSON lines):
```
{"job_id": 35, "run_id": 13, "worker_id": "DESKTOP-N3ELC32:29236:t1", "event": "job.claimed", "timestamp": "2026-11-18T08:54:48.489212Z"}
{"start_url": "http://slow-site.fixture.test/", "pages": 2, "stopped_reason": "completed", "ms": 8814, "event": "crawl.finished", "job_id": 35, ...}
{"status": "cancelled", "error_code": "CANCELLED", "reason": "run cancelled; stopped before saving results", "event": "job.finished", "job_id": 35, ...}
```

## Result: PASS

| Check | Result |
|---|---|
| Queued jobs cancelled at once | 4 of 4 (`cancelled_now=4`), never claimed |
| Run while the job is still running | `cancelling` |
| Running job ends `cancelled`, no classifications | yes (attempt 1 `failed` / `CANCELLED`, 0 classifications) |
| Run final status | `cancelled` (never `completed`), `finished_at` set |
| Cancelling a finished run | 409 `RUN_FINISHED` |

The worker checks for a cancel before crawling and again after crawling (before the AI call), so a cancel never
spends AI quota once noticed. Also covered by automated tests: `tests/test_runs.py::test_cancel_cancels_queued_jobs_and_waits_for_running_ones`,
`tests/test_worker.py::test_cancel_between_crawl_and_classify`.

## Limits

- A job is not interrupted in the MIDDLE of a crawl or an AI call; it stops at the next check (here after an 8-s
  crawl). Worst case it finishes the current step first.
