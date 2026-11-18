# Evidence index

Every file in this folder, what it proves, and what kind of data it uses.

- **REAL** = real websites and/or real AI providers (Gemini / Groq), live system.
- **FIXTURE** = local fixture websites (`fixtures/sites/`, served by `fixtures/server.py`) - hand-written test pages.
- **SYNTHETIC** = generated rows and/or the deterministic fake AI provider (`fake-keyword-v1`).
- **TEST** = an automated test against the real PostgreSQL database (fakes for crawling / AI).

All numbers in these files come from real runs on 2026-11-17/18 (Windows 11, PostgreSQL 18); nothing is estimated.

| File | Proves (brief requirement / scenario) | Data |
|---|---|---|
| [scenario_A_worker_crash.md](scenario_A_worker_crash.md) | **Scenario A** - worker hard-killed mid-job: lease expires, attempt `abandoned`, job finished once by another worker, exactly 7 answers | REAL (agtegra.com, Gemini) |
| [scenario_C_duplicates.md](scenario_C_duplicates.md) | **Scenario C** - no duplicate companies / runs / jobs / answers (Idempotency-Key, unique domain, one active job per company) | REAL |
| [scenario_D_ssrf_and_injection.md](scenario_D_ssrf_and_injection.md) | **Scenario D** - redirect to a private IP blocked (`BLOCKED_UNSAFE`, not retried); prompt injection stored as data, not obeyed | FIXTURE sites + REAL Gemini |
| [scenario_E_override_conflict.md](scenario_E_override_conflict.md) | **Scenario E** - human correction wins over a disagreeing new scan; conflict flagged; override row unchanged | REAL (agtegra.com, Gemini) |
| [scenario_F_db_write_failure.md](scenario_F_db_write_failure.md) | **Scenario F** - final save fails half-way: everything rolled back, job re-queued with backoff, retry succeeds | TEST |
| [scenario_G_concurrent_edits.md](scenario_G_concurrent_edits.md) | **Scenario G** - two reviewers save at once: exactly one wins, the other gets 409 (optimistic locking + unique rule) | TEST |
| [scenario_H_ambiguous_unavailable.md](scenario_H_ambiguous_unavailable.md) | **Scenario H** - outdated evidence -> `possible`; broken / empty / robots-blocked site -> failed `NO_CONTENT`, never "not found" | FIXTURE sites + REAL Gemini |
| [scenario_I_cancel.md](scenario_I_cancel.md) | **Scenario I** - cancel while running: queued jobs cancelled at once, running job ends cancelled with no answers, run `cancelled` | FIXTURE sites + SYNTHETIC (fake AI) |
| [scenario_J_migration.md](scenario_J_migration.md) | **Scenario J** - schema migration up / down / up keeps data, old code keeps working, `alembic check` clean | REAL migrations on `bep_test` |
| [hour2_classifier.md](hour2_classifier.md) | Evidence-backed classification on a real site; forced and real-world Gemini -> Groq fallback | REAL (agtegra.com) |
| [quality_evaluation.md](quality_evaluation.md) | Rules applied as the brief describes (precision / recall / confusion on 9 labelled sites). **Prompt was tuned on this same set - no held-out set; not a real-world accuracy figure** | FIXTURE sites + REAL Gemini |
| [real_site_pilot.md](real_site_pilot.md) | 15 real companies end to end, honest failures (403, TLS, AI quota), **manual evidence audit = the real-world quality signal** | REAL (15 websites, Gemini + Groq) |
| [bulk_intake_1000.md](bulk_intake_1000.md) | Intake at scale: 1,000-row CSV in one request (~1.4 s), every row accepted / duplicate / invalid with a reason; no crawling | SYNTHETIC rows |
| [synthetic_load_100.md](synthetic_load_100.md) | Platform throughput and correctness at 100 jobs with 2 threads: no duplicates, exactly 7 answers per job, retries | FIXTURE sites + SYNTHETIC (fake AI) |
| [export_sample.md](export_sample.md) | CSV / JSON export of final answers (human wins), corrections audit trail | REAL |
| [metrics_snapshot.md](metrics_snapshot.md) | `GET /api/metrics` after all runs (retries, durations, AI calls / tokens, cost "unknown") | Mixed (REAL + FIXTURE + SYNTHETIC totals) |

Inputs used by these files: `sample-data/labelled_fixtures.csv` (expected answers for the fixture sites),
`sample-data/real_companies.csv` (pilot websites with sources), `sample-data/bulk_1000.csv` (generated, seed 42).
Scripts: `scripts/evaluate.py`, `scripts/real_pilot.py`, `scripts/load_test.py`, `scripts/make_bulk_csv.py`.

Test data is labelled in the database (`companies.source` = `fixture` / `synthetic`), shown as a grey "Test data"
badge in the UI and can be hidden (`include_test=false`).
