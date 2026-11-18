# Test results and coverage

Run on 2026-11-18, Windows 11, Python 3.13, PostgreSQL 18 (`bep_test`): `pytest --cov=app --cov-report=term` in
`backend/`. Tests use the real database; crawling and AI are faked (local fixtures / fake providers) except where a
file in this folder says REAL.

**Result: 250 passed in 76.55 s. Line coverage 88 % (2,533 statements, 314 missed).**
Frontend: 12 tests (`frontend/`, backend faked with respx).

| Module | Stmts | Miss | Cover | Critical path |
|---|---|---|---|---|
| app\crawler\crawl.py | 112 | 0 | 100% | page discovery, limits |
| app\crawler\fetch.py | 136 | 3 | 98% | redirects, retries, size limits |
| app\crawler\safety.py | 52 | 7 | 87% | SSRF checks |
| app\crawler\robots.py | 27 | 1 | 96% | robots.txt |
| app\classifier\validate.py | 69 | 0 | 100% | verbatim-quote validation |
| app\classifier\pipeline.py | 160 | 9 | 94% | retries, fallback, quota breaker |
| app\classifier\providers.py | 125 | 21 | 83% | error classification (real SDK clients not called in tests) |
| app\classifier\select.py | 60 | 2 | 97% | passage selection |
| app\worker\leases.py | 57 | 3 | 95% | claim, lease, recovery |
| app\worker\process.py | 114 | 9 | 92% | fenced finalize, backoff |
| app\services\overrides.py | 38 | 0 | 100% | optimistic locking |
| app\services\answers.py | 74 | 6 | 92% | human-wins final answer |
| app\services\runs.py | 135 | 16 | 88% | idempotent runs, cancel, retry |
| app\services\ingest.py | 83 | 1 | 99% | CSV validation, dedup |
| app\api\* (auth, companies, exports, overrides, runs, stats, uploads, errors) | 366 | 22 | 94% | HTTP layer |
| app\db\models.py | 194 | 0 | 100% | schema |

**Not covered by automated tests (0 %):** `app\worker\main.py` (process entry point: threads, signals - exercised
live in scenarios A and I), `app\classifier\cli.py` and `app\crawler\cli.py` (manual command-line tools, used for
the live checks). `app\db\seed.py` 60 %.

Coverage measures lines executed, not correctness; the scenario files show the behaviour.
