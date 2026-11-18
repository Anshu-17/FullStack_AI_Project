# Scenario E - a human correction vs. a new automated scan that disagrees

**Question:** a reviewer corrected an answer. Later the company is scanned again and the AI says something
else. Which answer wins, and is the disagreement visible?
**Answer shown here:** the human answer stays the final answer (provenance `human`); the new automated
answer is saved next to it with `conflicts_with_override = true`, the UI and exports show the conflict, and the
override row is never changed by a scan.

Date: 2026-11-18 (times UTC). Live system: API + one worker + Streamlit, PostgreSQL 18, real crawl of
agtegra.com and real Gemini (`gemini-2.5-flash`). Logged in as `reviewer@demo.local` (password passed only as
an environment variable of the command, never stored).

## Steps

1. Read Agtegra's current Grain answer (`GET /api/companies/1`).
2. Correct Grain as a reviewer: `POST /api/companies/1/overrides` with `new_status = "possible"`, a reason, and
   the `expected_version` shown (0).
3. Rescan: `POST /api/companies/1/rescan` (Idempotency-Key) and wait for the worker to finish.
4. Read the final answer again and inspect the database.

## Expected

- After step 2: final Grain = `possible`, provenance `human`, override version 1, `old_status` = the answer shown.
- After step 3: the new classification is saved, and because it differs from the human answer it has
  `conflicts_with_override = true`.
- The final answer is still the human one, `conflict = true`, and the override row is unchanged.

## Observed

```
[08:26:00Z] POST /api/auth/login reviewer@demo.local -> HTTP 200 user={'id': 1, 'email': 'reviewer@demo.local', 'role': 'reviewer'}
[08:26:00Z] BEFORE: grain final=not_found provenance=site version=0 automated=not_found
    DB overrides(grain): []
    DB latest grain classifications (id, job, status, conflicts_with_override, job status):
        [(51, 8, 'not_found', False, 'review_required'), (44, 6, 'yes', False, 'review_required'), (30, 5, 'yes', False, 'review_required')]

[08:26:02Z] POST /api/companies/1/overrides (reviewer) -> HTTP 201
    {"override": {"id": 1, "version": 1, "old_status": "not_found", "new_status": "possible"},
     "answer": {"category": "grain", "status": "possible", "provenance": "human",
                "explanation": "Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.", ...}}
    DB overrides(grain): [(1, 1, 'not_found', 'possible', 'Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.', 1, '08:26:02Z')]

[08:26:02Z] POST /api/companies/1/rescan -> HTTP 201
    {"run_id": 8, "status": "queued", "total_items": 1, "skipped": [], "created": true}
[08:26:02Z] run 8: queued progress 0/1
[08:26:04Z] run 8: running progress 0/1
[08:26:36Z] run 8: completed progress 1/1

[08:26:36Z] AFTER: grain final=possible provenance=human conflict=True version=1
    automated (new scan): status=yes job=9 conflicts_with_override_at_scan=True
    override shown: {"status": "possible", "reason": "Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.", "reviewer_id": 1, "version": 1, ...}
    DB overrides(grain): [(1, 1, 'not_found', 'possible', 'Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.', 1, '08:26:02Z')]
    DB latest grain classifications (id, job, status, conflicts_with_override, job status):
        [(58, 9, 'yes', True, 'review_required'), (51, 8, 'not_found', False, 'review_required'), (44, 6, 'yes', False, 'review_required')]
    override rows unchanged: True
```

The new scan (job 9) found Grain = `yes` with the verified quote "CASH BIDS AND FUTURES CASH BIDS FUTURES"
from agtegra.com/products-services/grain. It is stored, flagged as conflicting, and shown next to the human
answer; it does not replace it.

The export downloaded right after (see `export_sample.md`) shows the same: Agtegra
`grain_status = possible, grain_source = human, grain_conflict = yes`, and the JSON contains both the human
answer and the automated answer with its evidence.

In the UI (Company detail), the Grain section shows the Human badge, the reviewer's reason, the note
"⚠ Conflicts with the latest automated scan: the scan says Yes, the reviewer says Possible", and the automated
answer with its quote underneath. The job is `review_required`.

## Result: PASS

## Also covered by automated tests

- `backend/tests/test_overrides.py::test_scenario_e_new_scan_disagrees_human_answer_stays` - fake classifier
  says `not_found` after a human `yes`: new row has `conflicts_with_override = true`, final answer stays human,
  override row unchanged.
- `backend/tests/test_classify_pipeline.py::test_disagreeing_override_is_flagged_and_left_unchanged`.
- `backend/tests/test_answers.py::test_override_wins_with_provenance_human_and_conflict_flag`.
- `frontend/tests/test_pages.py::test_detail_shows_evidence_sources_and_conflict`.
