# SYNTHETIC workload - 100 jobs (local fixtures + FAKE AI provider)

> **Synthetic.** Websites are local fixture pages (`fixtures/sites/`, numbered copies such as `clear-coop-305.fixture.test`) and the AI is the deterministic keyword provider `fake-keyword-v1` (no network, no AI cost). It measures the PLATFORM - API, queue, worker, crawler, validation, database - not real-world crawl or AI latency. Every number below is read from the database after the run.

- Date: 2026-11-18 08:59 UTC; run #14; upload #9 (source=synthetic, counts {'total': 100, 'accepted': 100, 'existing': 0, 'duplicate': 0, 'invalid': 0})
- Machine: Windows-11-10.0.26300-SP0, Python 3.13.5, local PostgreSQL 18; API, worker and fixture server on the same machine
- Worker: ONE process, `WORKER_CONCURRENCY=2` threads, lease 120 s; test-only settings in the command environment: `AI_PROVIDER=fake`, `CRAWL_FIXTURE_SERVER=127.0.0.1:8765`, `CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test`, `JOB_BACKOFF_BASE_SECONDS=1` (retry waits 1 s, 2 s + jitter instead of 10 s, 20 s)
- Mix: 100 jobs, 90 on content fixture sites, 10 on `broken-site` (every page answers 500 -> NO_CONTENT -> retried, then failed)

## Results

| measure | value |
|---|---|
| total time (run created -> finished) | 87.1 s |
| processing time (first claim -> finished) | 85.7 s |
| throughput | 70.0 jobs/min (all 100 jobs incl. retries) |
| job latency, successful jobs (claim -> finished) | p50 0.74 s, p95 0.93 s, max 1.78 s |
| outcomes by job status | {'completed': 90, 'failed': 10} |
| failures by error code | {'NO_CONTENT': 10} |
| attempts by status | {'succeeded': 90, 'failed': 30} |
| retries (attempts beyond the first) | 20 |
| successful jobs with exactly 7 classifications | 90 of 90 |
| duplicate (job, category) answers | 0 |
| failed jobs with any classification saved | 0 |
| AI calls (provider / model / outcome) | [('fake', 'fake-keyword-v1', 'ok', 90)] |

## Reading the numbers

- The broken-site jobs each took 3 attempts (2 retries) and then failed with `NO_CONTENT`; their failure never produced answers.
- Latency here is dominated by crawling the local fixture pages and by the database work; with a real AI provider each job also waits for the model (5-15 s per call in the real runs), so real throughput is much lower and bounded by AI rate limits (free tier).
- Exactly-7-classifications and zero duplicates are guaranteed by the unique `(job_id, category)` rule and the lease-fenced finalize; this run confirms it at 100 jobs with 2 concurrent threads.
