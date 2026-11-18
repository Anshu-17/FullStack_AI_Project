# API

Base URL: `http://localhost:8000` locally, `https://<bep-api>.onrender.com` when deployed. Interactive docs (OpenAPI /
Swagger): **`/docs`**; machine-readable spec: **`/openapi.json`** (exported copy: [`docs/openapi.json`](openapi.json)).

## Authentication

1. `POST /api/auth/login` with `{"email": "...", "password": "..."}` ->
   `{"access_token": "...", "token_type": "bearer", "expires_in": 28800, "user": {"id", "email", "role"}}`.
2. Send `Authorization: Bearer <access_token>` on every other `/api` call. Tokens are HS256 JWTs signed with
   `JWT_SECRET`, valid 8 hours; the user's role and active flag are re-read from the database on every request.
3. Roles: **viewer** = read + export; **reviewer** = also add companies, start / cancel / retry runs, correct answers.

Open without login: `/health`, `/ready`, `/docs`, `/openapi.json`, `POST /api/auth/login`.

## Endpoints

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | - | process is up (no database access) |
| GET | `/ready` | - | database reachable + current migration (503 if not) |
| POST | `/api/auth/login` | - | log in, get a token (rate limit 10/min per IP) |
| GET | `/api/auth/me` | viewer | the current user |
| POST | `/api/uploads` | reviewer | upload a CSV (`company_name`, `website`; optional form field `source`); returns counts + rejected rows (20/min) |
| GET | `/api/uploads/{id}/rows` | viewer | per-row results (`?result=accepted\|existing\|duplicate\|invalid`) |
| POST | `/api/companies` | reviewer | add one company (201 created / 200 already existed) |
| GET | `/api/companies` | viewer | list with final answers (`?search=&category=&status=&include_test=`) |
| GET | `/api/companies/{id}` | viewer | final 7 answers with evidence, versions, conflicts, scan history |
| POST | `/api/companies/{id}/rescan` | reviewer | start a one-company run (optional `Idempotency-Key`) |
| POST | `/api/companies/{id}/overrides` | reviewer | correct an answer (optimistic locking with `expected_version`) |
| GET | `/api/companies/{id}/overrides` | viewer | correction history, newest first |
| POST | `/api/runs` | reviewer | start a run: `{"company_ids": [...]}` or `{"upload_id": N}` or `{"all_companies": true}` |
| GET | `/api/runs` | viewer | runs with counts and progress |
| GET | `/api/runs/{id}` | viewer | one run: status, counts per job status, progress from the database |
| GET | `/api/runs/{id}/items` | viewer | the run's jobs (`?status=`) with attempts and last error |
| POST | `/api/runs/{id}/cancel` | reviewer | cancel queued jobs now; running ones at their next check |
| POST | `/api/runs/{id}/retry-failed` | reviewer | re-queue failed / cancelled jobs of the run |
| GET | `/api/jobs/{id}` | viewer | job with attempts, status events, pages fetched |
| POST | `/api/jobs/{id}/retry` | reviewer | re-queue one failed / cancelled job (409 otherwise) |
| GET | `/api/exports` | viewer | final answers as CSV or JSON (`?format=csv\|json` + list filters), dated file name |
| GET | `/api/exports/overrides` | viewer | all corrections (audit trail) as CSV or JSON |
| GET | `/api/stats` | viewer | dashboard counts |
| GET | `/api/metrics` | viewer | jobs by status, retries, durations, AI calls by provider/outcome, tokens, cost (or null) |

Rate limits: login 10/min, uploads 20/min, everything else 300/min per client IP.

## Response shapes

**Errors** (every 4xx/5xx, including validation, 401, 403, 404, 409, 429):

```json
{"error": {"code": "VERSION_CONFLICT", "message": "Someone else changed this answer after you opened it. Reload to see the latest version.",
           "details": {"current_version": 1, "changed_by": "reviewer@demo.local", "changed_at": "2026-11-18T08:26:02+00:00", "current_status": "possible"}}}
```

422 validation errors list the bad fields: `"details": {"fields": [{"field": "body.website", "message": "Field required"}]}`.
Common codes: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `RATE_LIMITED`, `NOTHING_TO_RUN`,
`ALREADY_IN_PROGRESS`, `RUN_FINISHED`, `JOB_NOT_RETRYABLE`, `VERSION_CONFLICT`, `NOTHING_TO_REMOVE`,
`MISSING_COLUMNS`, `FILE_TOO_LARGE`, `NOT_UTF8`, `TOO_MANY_ROWS`, `INTERNAL_ERROR` (with `request_id`).

**Lists:** `{"items": [...], "page": 1, "page_size": 50, "total": 123}`; `?page=` (from 1) and `?page_size=`
(1-200, default 50).

## Idempotency

`POST /api/runs` and `POST /api/companies/{id}/rescan` accept an `Idempotency-Key` header. The first call creates the
run (201); any later call with the same key returns **the same run** (200, `"created": false`) - the key is UNIQUE in
the database, so even two simultaneous requests create one run. Duplicate company ids in one request collapse; a
company that already has a queued/running job is skipped (`"skipped": [{"company_id": 1, "reason": "already_in_progress"}]`),
and if nothing is left the answer is 409 `NOTHING_TO_RUN`. Live proof: `docs/evidence/scenario_C_duplicates.md`.

## Examples

```bash
API=http://localhost:8000
TOKEN=$(curl -s -X POST $API/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"reviewer@demo.local","password":"<password>"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

curl -s -X POST $API/api/uploads -H "$AUTH" -F file=@sample-data/real_companies.csv     # upload
curl -s -X POST $API/api/runs -H "$AUTH" -H 'Idempotency-Key: demo-1' \
  -H 'Content-Type: application/json' -d '{"upload_id": 1}'                           # start research
curl -s $API/api/runs/1 -H "$AUTH"                                                    # progress
curl -s "$API/api/companies?category=grain&status=yes" -H "$AUTH"                     # filter final answers
curl -s -X POST $API/api/companies/1/overrides -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"category":"grain","new_status":"possible","reason":"checked by phone","expected_version":0}'
curl -s "$API/api/exports?format=csv" -H "$AUTH" -o companies.csv                     # export
```

Final answers: the latest human correction wins (provenance `human`), else the latest finished scan (`site` or
`rule`), else `null` ("not scanned yet" - never "not found"). Each answer carries `version` (send it back as
`expected_version`), the automated answer with its verified evidence, and `conflict`.
