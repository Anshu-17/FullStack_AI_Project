# Scenario B - AI API times out, rate-limits, or returns invalid output

**Brief acceptance:** failures classified, bounded retries shown, final status meaningful, no fabricated successful
answer.

**Answer shown here:** every AI failure gets an error code (`AI_TIMEOUT`, `AI_RATE_LIMITED`, `AI_INVALID_OUTPUT`,
`AI_AUTH`, `AI_ERROR`, `AI_QUOTA_EXHAUSTED`), is recorded as one `ai_usage` row per call, is retried at most 3 times
per provider (never for errors a retry cannot fix), then falls back to the next provider. If every provider fails the
job is re-queued with backoff, and after its attempt ceiling it ends `failed` with `AI_UNAVAILABLE` and **no
classification rows** - never an invented answer.

## How it works

| Failure | Code | Retried? | Then |
|---|---|---|---|
| timeout / connection error | `AI_TIMEOUT` | yes, same provider, up to 3 attempts, exponential backoff + jitter | next provider |
| per-minute 429 | `AI_RATE_LIMITED` | yes (as above) | next provider |
| daily quota 429 | `AI_QUOTA_EXHAUSTED` | no; provider skipped for 30 min by this worker (`skipped_quota` rows) | next provider |
| unparseable / incomplete JSON, a category missing, answer cut off at the token limit | `AI_INVALID_OUTPUT` | yes (as above) | next provider |
| bad API key / permission | `AI_AUTH` | no | next provider |
| unknown model (404) / other 4xx | `AI_ERROR` | no | next provider |
| 5xx | `AI_ERROR` | yes | next provider |
| all providers failed | job error `AI_UNAVAILABLE` | job re-queued with `min(300, 10 x 2^(n-1)) s` + jitter, max 3 attempts | `failed`, visible in the run, manual retry possible |

Code: `backend/app/classifier/providers.py` (error classification), `backend/app/classifier/pipeline.py` (retries,
fallback, quota breaker), `backend/app/worker/process.py` (job backoff / attempt ceiling).

## Live evidence (REAL providers)

**1. Forced failure, unknown model, job #5** (`GOOGLE_MODEL=does-not-exist`), from [hour2_classifier.md](hour2_classifier.md):

| ai_usage id | provider | model | outcome | error_code | tokens in / out | latency ms | created (UTC) |
|---|---|---|---|---|---|---|---|
| 8 | google | does-not-exist | error | AI_ERROR | None / None | 288 | 2026-11-18 07:29:32 |
| 9 | groq | openai/gpt-oss-20b | ok | - | 4209 / 1549 | 2287 | 2026-11-18 07:29:43 |

One call, not retried (retrying cannot fix a missing model), then fallback; job `review_required`, 7 answers.

**2. Real invalid output, job #3** (not staged), from [hour2_classifier.md](hour2_classifier.md):

| ai_usage id | provider | model | outcome | error_code | tokens in / out | latency ms | created (UTC) |
|---|---|---|---|---|---|---|---|
| 3 | google | gemini-2.5-flash | invalid_output | AI_INVALID_OUTPUT | 4271 / 3419 | 14868 | 2026-11-18 07:24:23 |
| 4 | google | gemini-2.5-flash | invalid_output | AI_INVALID_OUTPUT | 4271 / 3814 | 15290 | 2026-11-18 07:24:58 |
| 5 | google | gemini-2.5-flash | invalid_output | AI_INVALID_OUTPUT | 4271 / 3419 | 14639 | 2026-11-18 07:25:15 |
| 6 | groq | openai/gpt-oss-20b | ok | - | 4212 / 1681 | 3048 | 2026-11-18 07:25:23 |

Exactly 3 bounded retries on Gemini, none of the invalid answers saved, then Groq.

**3. Real rate limits, 15-company pilot**, from [real_site_pilot.md](real_site_pilot.md): Gemini's free daily quota
(20 requests/model/day) was exhausted and Groq hit its per-minute limit. 4 jobs ended `failed` with `AI_UNAVAILABLE`
after their attempts (crawl fine, both AIs refused) - shown as failed, not as "not found". One manual retry
(`POST /api/jobs/{id}/retry`) of those 4 jobs succeeded on Groq. This run also led to the daily-quota breaker
(85 wasted Gemini 429 calls before it existed).

## Tests (TEST - fake providers, real PostgreSQL), run 2026-11-18

```
tests/test_classify_pipeline.py::test_timeouts_on_primary_then_success_on_fallback PASSED
tests/test_classify_pipeline.py::test_rate_limit_is_retried_then_succeeds PASSED
tests/test_classify_pipeline.py::test_missing_category_three_times_falls_back_to_second_provider PASSED
tests/test_classify_pipeline.py::test_cut_off_answer_is_invalid_output_and_retried PASSED
tests/test_classify_pipeline.py::test_daily_quota_error_cools_the_provider_down_for_later_jobs PASSED
tests/test_classify_pipeline.py::test_all_providers_fail_saves_no_classifications PASSED
tests/test_worker.py::test_ai_unavailable_backs_off_then_fails_and_never_saves_classifications PASSED
tests/test_classifier.py::test_error_classification[exc0-AI_TIMEOUT-True] PASSED
tests/test_classifier.py::test_error_classification[exc1-AI_TIMEOUT-True] PASSED
tests/test_classifier.py::test_error_classification[exc2-AI_RATE_LIMITED-True] PASSED
tests/test_classifier.py::test_error_classification[exc3-AI_AUTH-False] PASSED
tests/test_classifier.py::test_error_classification[exc4-AI_AUTH-False] PASSED
tests/test_classifier.py::test_error_classification[exc5-AI_ERROR-True] PASSED
tests/test_classifier.py::test_error_classification[exc6-AI_ERROR-False] PASSED
============================= 14 passed in 5.75s ==============================
```

(`True` / `False` = retryable or not.)

## Reproduce

```powershell
cd backend; .venv\Scripts\activate
# live: unknown model -> AI_ERROR once, then Groq
$env:GOOGLE_MODEL='does-not-exist'; python -m app.classifier.cli https://www.agtegra.com --name "Agtegra Cooperative" --quiet
# tests
pytest tests/test_classify_pipeline.py tests/test_classifier.py -k "timeout or rate_limit or missing_category or cut_off or daily_quota or all_providers_fail or error_classification"
pytest tests/test_worker.py -k ai_unavailable
```

## Known limitations

- A real AI **timeout** was not observed live; that path is proven by tests with a fake provider only.
- The quota breaker is in memory per worker process (not shared between processes) and was added after the pilot;
  it is proven by tests, not yet seen live.
- A call in flight when the worker is killed is not recorded in `ai_usage`.
