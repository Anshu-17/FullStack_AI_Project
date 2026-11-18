# Scenario H - ambiguous evidence vs. an unavailable website

**FIXTURE data, REAL pipeline** (real crawler + real Gemini). Date: 2026-11-18 (UTC).

**Question:** does the system tell apart "the evidence is unclear" (answer `possible`) from "we could not read the
website at all" (a failed job - NOT "not found")?
**Answer shown here:** yes.

| Situation | What the system records |
|---|---|
| Outdated evidence ("our elevator closed in 2015") | grain = **possible**, quote saved, job `review_required` |
| Every page answers 500 (broken-site) | job **failed `NO_CONTENT`** after 3 attempts with backoff; answers stay **null = "not scanned"** |
| Homepage is empty (empty-site) | same: **failed `NO_CONTENT`**, answers null |
| robots.txt disallows everything (robots-blocked) | pages `robots_disallowed` -> **failed `NO_CONTENT`**, answers null |

A crawl failure is never turned into seven "not_found" answers: "not_found" means "we read the site and found no
evidence", which would be a false statement about a site we could not read.

Live system on Windows 11 / PostgreSQL 18: API (`uvicorn`), one worker process (2 threads), the local fixture server (`python fixtures/server.py`). The worker got the TEST-ONLY settings `CRAWL_FIXTURE_SERVER=127.0.0.1:8765`, `CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test` and, to keep the demo short, `JOB_BACKOFF_BASE_SECONDS=2` (default 10) - in its command environment only, `.env` untouched. Companies were uploaded through `POST /api/uploads` with `source=fixture` (shown as "Test data").

## Observed - run 10 (same run as scenario D)

```
[08:49:48Z] POST /api/uploads (source=fixture) -> HTTP 201 counts={'total': 6, 'accepted': 4, 'existing': 2, 'duplicate': 0, 'invalid': 0}
[08:49:48Z] POST /api/runs -> HTTP 201 {"run_id": 10, "status": "queued", "total_items": 6, "skipped": [], "created": true}
[08:49:48Z] run 10 queued 0/6 | Redirect Co-op: queued (att 0); Summit Ag Supply: queued (att 0); Lakeview Cooperative: queued (att 0); Broken Site Co-op: queued (att 0); Empty Site Co-op: queued (att 0); Hidden Acres Co-op: queued (att 0)
[08:49:49Z] run 10 running 0/6 | Redirect Co-op: running (att 1); Summit Ag Supply: running (att 1); Lakeview Cooperative: queued (att 0); Broken Site Co-op: queued (att 0); Empty Site Co-op: queued (att 0); Hidden Acres Co-op: queued (att 0)
[08:49:51Z] run 10 running 1/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: running (att 1); Lakeview Cooperative: running (att 1); Broken Site Co-op: queued (att 0); Empty Site Co-op: queued (att 0); Hidden Acres Co-op: queued (att 0)
[08:50:01Z] run 10 running 2/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: running (att 1); Broken Site Co-op: running (att 1); Empty Site Co-op: queued (att 0); Hidden Acres Co-op: queued (att 0)
[08:50:02Z] run 10 running 3/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: running (att 1); Empty Site Co-op: running (att 1); Hidden Acres Co-op: queued (att 0)
[08:50:03Z] run 10 running 3/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: running (att 1); Empty Site Co-op: queued (att 1); Hidden Acres Co-op: running (att 1)
[08:50:04Z] run 10 running 3/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: queued (att 1); Empty Site Co-op: queued (att 1); Hidden Acres Co-op: queued (att 1)
[08:50:06Z] run 10 running 3/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: running (att 2); Empty Site Co-op: queued (att 2); Hidden Acres Co-op: running (att 2)
[08:50:07Z] run 10 running 3/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: running (att 2); Empty Site Co-op: queued (att 2); Hidden Acres Co-op: queued (att 2)
[08:50:10Z] run 10 running 3/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: queued (att 2); Empty Site Co-op: running (att 3); Hidden Acres Co-op: queued (att 2)
[08:50:11Z] run 10 running 4/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: queued (att 2); Empty Site Co-op: failed (att 3); Hidden Acres Co-op: queued (att 2)
[08:50:13Z] run 10 running 4/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: queued (att 2); Empty Site Co-op: failed (att 3); Hidden Acres Co-op: running (att 3)
[08:50:14Z] run 10 running 5/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: queued (att 2); Empty Site Co-op: failed (att 3); Hidden Acres Co-op: failed (att 3)
[08:50:15Z] run 10 running 5/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: running (att 3); Empty Site Co-op: failed (att 3); Hidden Acres Co-op: failed (att 3)
[08:50:18Z] run 10 completed_with_errors 6/6 | Redirect Co-op: failed (att 1); Summit Ag Supply: completed (att 1); Lakeview Cooperative: completed (att 1); Broken Site Co-op: failed (att 3); Empty Site Co-op: failed (att 3); Hidden Acres Co-op: failed (att 3)
```

Failed jobs (no AI call is made when there is no usable text - `NO_CONTENT` is raised before the AI step):
```
--- job 22 Broken Site Co-op (http://broken-site.fixture.test/): status=failed last_error=NO_CONTENT msg='no page with usable text was crawled' classifications=0
    attempt 1: failed error=NO_CONTENT no page with usable text was crawled
    attempt 2: failed error=NO_CONTENT no page with usable text was crawled
    attempt 3: failed error=NO_CONTENT no page with usable text was crawled
    page http://broken-site.fixture.test/: outcome=http_error http=500
    event None -> queued: created in run 10
    event queued -> running: claimed (attempt 1)
    event running -> queued: NO_CONTENT: retry in 2 s (attempt 1 of 3)
    event queued -> running: claimed (attempt 2)
    event running -> queued: NO_CONTENT: retry in 4 s (attempt 2 of 3)
    event queued -> running: claimed (attempt 3)
    event running -> failed: NO_CONTENT: no attempts left

--- job 23 Empty Site Co-op (http://empty-site.fixture.test/): status=failed last_error=NO_CONTENT msg='no page with usable text was crawled' classifications=0
    attempt 1: failed error=NO_CONTENT no page with usable text was crawled
    attempt 2: failed error=NO_CONTENT no page with usable text was crawled
    attempt 3: failed error=NO_CONTENT no page with usable text was crawled
    page http://empty-site.fixture.test/: outcome=empty http=200
    event None -> queued: created in run 10
    event queued -> running: claimed (attempt 1)
    event running -> queued: NO_CONTENT: retry in 2 s (attempt 1 of 3)
    event queued -> running: claimed (attempt 2)
    event running -> queued: NO_CONTENT: retry in 4 s (attempt 2 of 3)
    event queued -> running: claimed (attempt 3)
    event running -> failed: NO_CONTENT: no attempts left

--- job 24 Hidden Acres Co-op (http://robots-blocked.fixture.test/): status=failed last_error=NO_CONTENT msg='no page with usable text was crawled' classifications=0
    attempt 1: failed error=NO_CONTENT no page with usable text was crawled
    attempt 2: failed error=NO_CONTENT no page with usable text was crawled
    attempt 3: failed error=NO_CONTENT no page with usable text was crawled
    page http://robots-blocked.fixture.test/: outcome=robots_disallowed http=None
    event None -> queued: created in run 10
    event queued -> running: claimed (attempt 1)
    event running -> queued: NO_CONTENT: retry in 2 s (attempt 1 of 3)
    event queued -> running: claimed (attempt 2)
    event running -> queued: NO_CONTENT: retry in 5 s (attempt 2 of 3)
    event queued -> running: claimed (attempt 3)
    event running -> failed: NO_CONTENT: no attempts left
```

Final answers of the three unreadable sites (null = not scanned, NOT not_found):
```
final answers Broken Site Co-op: {'accounting': None, 'agronomy': None, 'grain': None, 'energy': None, 'feed': None, 'gas_station': None, 'retail_store': None}
final answers Empty Site Co-op: {'accounting': None, 'agronomy': None, 'grain': None, 'energy': None, 'feed': None, 'gas_station': None, 'retail_store': None}
final answers Hidden Acres Co-op: {'accounting': None, 'agronomy': None, 'grain': None, 'energy': None, 'feed': None, 'gas_station': None, 'retail_store': None}
```

## Observed - outdated evidence

In run 10 (prompt `p2`) the model answered grain `not_found` for the outdated elevator:
```
final answers Lakeview Cooperative: {'accounting': 'yes', 'agronomy': 'yes', 'grain': 'not_found', 'energy': 'not_found', 'feed': 'not_found', 'gas_station': 'not_found', 'retail_store': 'not_found'}
```
That did not follow the brief's "outdated -> possible" rule (the labelled evaluation showed the same miss).
Prompt `p3` added one explicit rule ("if a passage says the company USED TO offer something, answer possible,
quote it"). The same fixture was then rescanned through the live API and worker:
```
[08:54:01Z] POST /api/companies/9/rescan -> 201 {'run_id': 12, 'status': 'queued', 'total_items': 1, 'skipped': [], 'created': True}
[08:54:22Z] run 12: completed; job 34: review_required
  accounting    yes        rule  prompt=None quotes=[]
  agronomy      yes        site  prompt=p3 quotes=['Lakeview Cooperative sells seed and fertilizer and offers custom spraying to members.']
  grain         possible   site  prompt=p3 quotes=['Our grain elevator in Lakeview operated from 1952 until it closed in 2015.']
  energy        not_found  site  prompt=p3 quotes=[]
  feed          not_found  site  prompt=p3 quotes=[]
  gas_station   not_found  site  prompt=p3 quotes=[]
  retail_store  not_found  site  prompt=p3 quotes=[]
```

## Result: PASS (with prompt p3)

Also covered by automated tests: `tests/test_classify_pipeline.py::test_no_usable_pages_raises_no_content_without_calling_ai`,
`tests/test_worker.py::test_ai_unavailable_backs_off_then_fails_and_never_saves_classifications`,
`tests/test_fixtures_and_fake.py::test_robots_blocked_and_broken_and_empty_sites`, `tests/test_robots.py`.

## Limits

- Backoff base was 2 s for this demo (default 10 s -> 10 s, 20 s, ... max 300 s, +0-25 % jitter).
- A site that only renders with JavaScript would also look "empty" (no JS rendering) and end as `NO_CONTENT`.
