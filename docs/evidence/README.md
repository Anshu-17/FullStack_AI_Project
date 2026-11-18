# Evidence index

Every file in this folder, what it proves, and what kind of data it uses.

- **REAL** = real websites and/or real AI providers (Gemini / Groq), live system.
- **FIXTURE** = local fixture websites (`fixtures/sites/`, served by `fixtures/server.py`) - hand-written test pages.
- **SYNTHETIC** = generated rows and/or the deterministic fake AI provider (`fake-keyword-v1`).
- **TEST** = an automated test against the real PostgreSQL database (fakes for crawling / AI).

All numbers in these files come from real runs on 2026-11-17/18 (Windows 11, PostgreSQL 18); nothing is estimated.

## Scenarios (brief section 6)

The brief requires A-E to be demonstrated and F-J tested or design-explained.

| ID | Brief condition | File | Shown how | Data |
|---|---|---|---|---|
| A | worker crash mid-batch | [scenario_A_worker_crash.md](scenario_A_worker_crash.md) | **demonstrated** - worker hard-killed mid-job: lease expires, attempt `abandoned`, job finished once by another worker, exactly 7 answers | REAL (agtegra.com, Gemini) |
| B | AI provider timeout / rate limit / malformed output (retries, then failed - never invented) | [scenario_B_ai_failures.md](scenario_B_ai_failures.md) | **demonstrated** - live unknown-model error, live 3x invalid output then fallback, live rate limits -> `AI_UNAVAILABLE` failed jobs; timeouts by test | REAL + TEST |
| C | duplicate and concurrent submission | [scenario_C_duplicates.md](scenario_C_duplicates.md) | **demonstrated** - no duplicate companies / runs / jobs / answers (Idempotency-Key, unique domain, one active job per company) | REAL |
| D | malicious site: redirect to private IP (SSRF) + prompt-injection text | [scenario_D_ssrf_and_injection.md](scenario_D_ssrf_and_injection.md) | **demonstrated** - redirect to a private IP blocked (`BLOCKED_UNSAFE`, not retried); injection stored as data, not obeyed | FIXTURE sites + REAL Gemini |
| E | human override conflicts with a rescan | [scenario_E_override_conflict.md](scenario_E_override_conflict.md) | **demonstrated** - human correction wins over a disagreeing new scan; conflict flagged; override row unchanged | REAL (agtegra.com, Gemini) |
| F | transient database failure during a write | [scenario_F_db_write_failure.md](scenario_F_db_write_failure.md) | tested - final save fails half-way: everything rolled back, job re-queued with backoff, retry succeeds | TEST |
| G | concurrent reviewer edits | [scenario_G_concurrent_edits.md](scenario_G_concurrent_edits.md) | tested - two reviewers save at once: exactly one wins, the other gets 409 (optimistic locking + unique rule) | TEST |
| H | weak / ambiguous / unavailable website evidence | [scenario_H_ambiguous_unavailable.md](scenario_H_ambiguous_unavailable.md) | demonstrated - outdated evidence -> `possible`; broken / empty / robots-blocked site -> failed `NO_CONTENT`, never "not found" | FIXTURE sites + REAL Gemini |
| I | cancellation during a run | [scenario_I_cancel.md](scenario_I_cancel.md) | demonstrated - queued jobs cancelled at once, running job ends cancelled with no answers, run `cancelled` | FIXTURE sites + SYNTHETIC (fake AI) |
| J | schema change / migration with rollback | [scenario_J_migration.md](scenario_J_migration.md) | demonstrated - migration up / down / up keeps data, old code keeps working, `alembic check` clean | REAL migrations on `bep_test` |

## Scale, quality and other tests (brief section 5)

| File | Proves | Data |
|---|---|---|
| [bulk_intake_1000.md](bulk_intake_1000.md) | **Bulk intake** - 1,000-row CSV in one request (~1.4 s), every row accepted / duplicate / invalid with a reason; no crawling in the request | SYNTHETIC rows |
| [real_site_pilot.md](real_site_pilot.md) | **Real-site pilot** - the 12 suggested companies + 3 added, end to end, honest failures (403, TLS, AI quota), **manual evidence audit = the real-world quality signal** | REAL (15 websites, Gemini + Groq) |
| [synthetic_load_100.md](synthetic_load_100.md) | **Controlled workload** - 100 independent jobs with 2 threads: no duplicates, exactly 7 answers per job, retries | FIXTURE sites + SYNTHETIC (fake AI) |
| [scenario_A_worker_crash.md](scenario_A_worker_crash.md) | **Recovery** - worker restart during in-flight work | REAL |
| [export_sample.md](export_sample.md) | **Search & export** - CSV / JSON export of final answers (human wins), corrections audit trail | REAL |
| [quality_evaluation.md](quality_evaluation.md) | **Quality** - precision / recall / confusion on 9 labelled fixture sites. **Prompt was tuned on this same set - no held-out set; not a real-world accuracy figure**. Manual audit: see real_site_pilot.md | FIXTURE sites + REAL Gemini |
| [metrics_snapshot.md](metrics_snapshot.md) | **Latency / cost** - `GET /api/metrics` after all runs (retries, durations, AI calls / tokens; cost "unknown", never estimated) | Mixed (REAL + FIXTURE + SYNTHETIC totals) |
| [hour2_classifier.md](hour2_classifier.md) | evidence-backed classification on a real site; forced and real-world Gemini -> Groq fallback | REAL (agtegra.com) |
| [crawl_coverage_improvement.md](crawl_coverage_improvement.md) | live-site finding fixed: Agfinity gas station / retail missed by the 8-page crawl; before / after with sitemap discovery + category-balanced selection; Agtegra regression check | REAL (2 websites, gemini-2.5-flash-lite) |
| [deployment_smoke_test.md](deployment_smoke_test.md) | live deployment: `/health`, `/ready` (database + migration), UI 200, 401 without login; author's manual login + real run | REAL (Render + Supabase) |
| [test_coverage.md](test_coverage.md) | 250 backend tests passing, 88 % line coverage, per critical module | TEST |

Inputs used by these files: `sample-data/labelled_fixtures.csv` (expected answers for the fixture sites),
`sample-data/real_companies.csv` (pilot websites with sources), `sample-data/bulk_1000.csv` (generated, seed 42).
Scripts: `scripts/evaluate.py`, `scripts/real_pilot.py`, `scripts/load_test.py`, `scripts/make_bulk_csv.py`.

Test data is labelled in the database (`companies.source` = `fixture` / `synthetic`), shown as a grey "Test data"
badge in the UI and can be hidden (`include_test=false`).
