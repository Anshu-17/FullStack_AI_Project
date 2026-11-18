# Metrics snapshot - GET /api/metrics

Taken **2026-11-18 09:24:02 UTC** as `viewer@demo.local`, right after the real-site pilot (HTTP 200).
Every number is computed from the database on request.

**Mixed data - read with care.** The database holds REAL runs (Agtegra / Insight FS tests, the 15-company pilot)
together with FIXTURE runs (evaluation, scenarios D/H/I) and SYNTHETIC data (1,000-row intake, 100-job load test
with the fake AI provider). Companies are labelled (`source`), but these totals cover everything.

| measure | value |
|---|---|
| companies | 1033 |
| runs | 15 |
| jobs by status | {'queued': 0, 'running': 0, 'completed': 112, 'review_required': 20, 'failed': 17, 'cancelled': 5} |
| classifications saved | 924 |
| human corrections | 1 |
| retries (attempts beyond the first) | 52 |
| job duration, successful jobs (first claim -> finish) | avg 21.8 s, median 0.8 s |
| AI calls by provider and outcome | {'fake': {'ok': 90}, 'google': {'error': 1, 'rate_limited': 91, 'ok': 30, 'invalid_output': 3}, 'groq': {'rate_limited': 50, 'error': 7, 'ok': 12}} |
| AI tokens | input 105,047 / output 81,732 |
| estimated AI cost | unknown (no prices configured - free tier; never estimated) |
| AI calls without a cost | 284 |

Notes:
- `fake` calls are the deterministic test provider of the synthetic load test (no real AI, no tokens).
- The many `rate_limited` rows are real: Gemini's free daily quota (20 requests/model/day) ran out during the pilot,
  and Groq's per-minute limit was hit (see `real_site_pilot.md`).
- The median job time is low because most successful jobs are the 90 synthetic load-test jobs (sub-second);
  real-site jobs took tens of seconds each.

Raw response:

```json
{
  "companies": 1033,
  "runs": 15,
  "jobs": {
    "queued": 0,
    "running": 0,
    "completed": 112,
    "review_required": 20,
    "failed": 17,
    "cancelled": 5
  },
  "classifications": 924,
  "overrides": 1,
  "retries": 52,
  "job_duration_seconds": {
    "avg": 21.8,
    "median": 0.8
  },
  "ai_calls": {
    "fake": {
      "ok": 90
    },
    "google": {
      "error": 1,
      "rate_limited": 91,
      "ok": 30,
      "invalid_output": 3
    },
    "groq": {
      "rate_limited": 50,
      "error": 7,
      "ok": 12
    }
  },
  "ai_tokens": {
    "input": 105047,
    "output": 81732
  },
  "est_cost_usd": null,
  "ai_calls_without_cost": 284
}
```
