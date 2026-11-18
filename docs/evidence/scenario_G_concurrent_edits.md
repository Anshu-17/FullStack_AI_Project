# Scenario G - two reviewers correct the same answer at the same time

**Question:** two reviewers open the same company, both see "Grain = Yes" (no correction yet, version 0),
and both save a different correction at the same moment. Does one silently overwrite the other?
**Answer shown here:** no. Exactly one save wins (version 1); the other gets `409 VERSION_CONFLICT`
saying who changed it and when, and nothing is overwritten.

Date: 2026-11-18. PostgreSQL 18, test database `bep_test`.

## How it is protected (optimistic locking)

1. The screen remembers the version it showed (`expected_version`, 0 = no correction yet).
2. On save, the backend compares it with the current highest version for (company, category).
   Different -> `409 VERSION_CONFLICT` with `{current_version, changed_by, changed_at, current_status}`.
3. If both saves read version 0 at the same instant, both try to insert version 1. The database's
   `UNIQUE (company_id, category, version)` rule accepts exactly one insert; the other fails and gets the
   same 409. Corrections are append-only (never updated or deleted), so the full history is kept.

Code: `backend/app/services/overrides.py`. UI: the Company detail page sends the version it displayed and
shows *"Someone else changed this answer (by <who> at <when>). Reload to see it."* on a 409.

## Test 1 - two real concurrent sessions

`tests/test_overrides.py::test_two_reviewers_racing_on_the_same_version_exactly_one_wins`:
two threads, each with its own database session (like two API requests), wait on a barrier and then both
save a correction for (company, `grain`) with `expected_version = 0`: reviewer 1 says `yes`, reviewer 2 says
`not_found`.

Command: `pytest -s tests/test_overrides.py::test_two_reviewers_racing_on_the_same_version_exactly_one_wins`
(run 3 times). Observed output, identical in all 3 runs:

```
SCENARIO G outcomes: {'r1@test.local': 'saved version 1', 'r2@test.local': '409 VERSION_CONFLICT (current_version=1, changed_by=r1@test.local)'}
SCENARIO G override rows: [(1, 'yes', 1)]
1 passed
```

Expected: exactly one `saved version 1`, exactly one 409, one row in the database. Observed: as expected.

## Test 2 - the worst timing, forced (the database rule is the last line of defence)

With real threads the second reviewer usually reads *after* the first commit, so test 1 mostly exercises
the version check. To prove the database rule also holds when both reads happen before either write,
`tests/test_overrides.py::test_race_lost_at_insert_is_caught_by_the_unique_rule` makes reviewer 2's first
read return "no correction yet" although reviewer 1 has already saved version 1. Reviewer 2's version check
therefore passes and it tries to insert version 1:

- the INSERT is rejected by `UNIQUE (company_id, category, version)` (IntegrityError),
- the service rolls back and answers `409 VERSION_CONFLICT` with `changed_by = race1@test.local`,
- the table still holds only `[(1, 'yes')]`.

Result: passed.

## Through the API

`tests/test_overrides.py::test_stale_expected_version_is_a_409_with_details` (HTTP level): a second save
with the stale `expected_version = 0` after version 1 exists returns

```json
{"error": {"code": "VERSION_CONFLICT",
           "message": "Someone else changed this answer after you opened it. Reload to see the latest version.",
           "details": {"current_version": 1, "changed_by": "reviewer@test.local",
                       "changed_at": "<timestamp>", "current_status": "yes"}}}
```

and the UI test `frontend/tests/test_pages.py::test_version_conflict_shows_someone_else_changed_it` checks the
page sends the displayed version and shows
"Someone else changed this answer (by other@demo.local at 2026-11-18 08:00 UTC). Reload to see it."

## Result: PASS
