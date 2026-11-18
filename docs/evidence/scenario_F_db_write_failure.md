# Scenario F - the database write fails while saving the results

**Automated test with REAL PostgreSQL** (`bep_test`), fake crawler and fake AI (no network). Date: 2026-11-18.

**Question:** if saving the final results fails half-way (database error, lost connection), can we end up with
half the answers saved, or a job marked "completed" without its answers?
**Answer shown here:** no. The 7 classifications, their evidence, the job status, the attempt result and the job
event are written in ONE transaction; when it fails, all of it is rolled back. The attempt is recorded as failed,
the job goes back to the queue with backoff, and the next attempt succeeds.

## Test

`backend/tests/test_worker.py::test_database_write_failure_at_finalize_saves_nothing_then_retry_succeeds`

1. A job is claimed and processed. During the final save, `save_classifications` adds the rows to the transaction
   and even sends them to the database (`flush`), then raises `RuntimeError("simulated database failure during
   commit")`.
2. Check the database: nothing saved, job status, attempt, backoff.
3. Pretend the backoff time has passed, process again (the crawler is replaced by one that fails the test if it is
   called - the pages saved by attempt 1 must be reused).

## Observed (pytest -s output)

```
SCENARIO F after failed save: {'status': 'queued', 'attempts': [(1, 'failed', 'INTERNAL_ERROR')], 'classifications': 0, 'error': 'INTERNAL_ERROR'}
SCENARIO F after retry: {'status': 'completed', 'attempts': [(1, 'failed', 'INTERNAL_ERROR'), (2, 'succeeded', None)], 'classifications': 7}
1 passed in 1.68s
```

## Expected vs observed

| Check | Result |
|---|---|
| Classifications after the failed save | 0 (the flushed rows were rolled back) |
| Job status after the failure | `queued` (not `completed`), `last_error_code = INTERNAL_ERROR` |
| Attempt 1 | `failed` / `INTERNAL_ERROR` |
| Retry delayed | `next_attempt_at` in the future (backoff 10 s base, +jitter) |
| Attempt 2 | `succeeded`, exactly 7 classifications, pages reused (no re-crawl) |

## Result: PASS

## Why it holds

- `worker/process.py::_finalize` opens one transaction, locks the job row (`SELECT ... FOR UPDATE`), checks the
  lease, adds classifications + evidence + status + attempt + event, then commits. Any exception before the commit
  leaves the `with SessionLocal()` block without committing -> PostgreSQL rolls everything back.
- The exception is caught by `process_job`, treated as a retryable `INTERNAL_ERROR`, and recorded in a NEW
  transaction (attempt failed, job re-queued with backoff), guarded by the same lease check.
- The unique `(job_id, category)` rule makes a duplicate set of answers impossible even if a retry raced.

## Limits

- If the database is down for good, the "record the failure" transaction fails too; the job then stays `running`
  until its lease expires and lease recovery re-queues it (scenario A).
