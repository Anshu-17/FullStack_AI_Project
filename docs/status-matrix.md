# Status matrix

Strict rule: **Built** = implemented AND demonstrated (test or live evidence). **Partial** = implemented but with a
known gap, or not demonstrated end to end. **Not built** = not implemented.

> The original brief is not stored in this repository; rows are taken from the requirements as they were given in
> the task briefs and referenced in the code (sections 2.2, 4.3, 4.5, 4.6). **[CHECK each row against the brief]**

## Product requirements

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| CSV upload with row-level validation (accepted / existing / duplicate / invalid + reason) | Built | [bulk_intake_1000.md](evidence/bulk_intake_1000.md), `tests/test_ingest.py` | 2 MB / 5,000 rows; 1,000 rows in ~1.4 s |
| Single-company add | Built | `tests/test_api.py` | 201 new / 200 existing |
| Deduplication by canonical domain | Built | [scenario_C](evidence/scenario_C_duplicates.md) | www / scheme / case / path variants collapse |
| Safe crawler (limits, robots.txt, SSRF) | Built | [scenario_D](evidence/scenario_D_ssrf_and_injection.md), crawler tests | 8 pages, depth 2, 1.5 MB/page, 5 MB/site, 120 s |
| JavaScript-rendered websites | Not built | - | plain HTTP only; JS-only sites give little text |
| Seven-category classification with verbatim evidence | Built | [real_site_pilot.md](evidence/real_site_pilot.md), [hour2_classifier.md](evidence/hour2_classifier.md) | 6 by AI + Accounting by rule |
| Yes / Possible / Not found semantics; "not scanned" distinct | Built | [scenario_H](evidence/scenario_H_ambiguous_unavailable.md) | failed crawls never become "not found" |
| Evidence validation (quotes must exist in crawled text) | Built | `tests/test_classify_pipeline.py`, pilot audit | relevance + 25-char/4-word rule for "yes" |
| Classification quality on real websites | Partial | [real_site_pilot.md](evidence/real_site_pilot.md) | 15 sites; 2 clear false negatives (Groq), 2 doubtful yes; no labelled real-world test set |
| Quality measured on a held-out set | Not built | [quality_evaluation.md](evidence/quality_evaluation.md) | 9 synthetic sites, prompt tuned on them |
| AI provider fallback | Built | [hour2_classifier.md](evidence/hour2_classifier.md), pilot | Gemini -> Groq; forced and real-world fallback |
| Daily-quota circuit breaker | Partial | `tests/test_classify_pipeline.py` | tested with fakes; not yet observed live; in-memory per worker process |
| Human review / corrections with audit history | Built | [scenario_E](evidence/scenario_E_override_conflict.md), [scenario_G](evidence/scenario_G_concurrent_edits.md) | append-only, optimistic locking |
| Final answer: human wins, conflict shown | Built | [scenario_E](evidence/scenario_E_override_conflict.md) | |
| Export CSV / JSON + corrections audit export | Built | [export_sample.md](evidence/export_sample.md) | |
| Login with reviewer / viewer roles | Built | `tests/test_auth.py`, Hour 4 live check | JWT, 8 h, no refresh tokens |
| User management screens | Not built | - | users from the seed script |
| Multi-tenancy (several organisations) | Not built | - | single organisation |
| CRM integration | Not built | [crm-mapping.md](crm-mapping.md) | field mapping proposed only |
| Rate limiting | Built | `tests/test_auth.py` | per API process (in memory) |
| Cost tracking | Partial | [metrics_snapshot.md](evidence/metrics_snapshot.md) | tokens recorded; cost NULL unless prices configured (free tier) |
| Metrics / observability (4.6) | Built | [metrics_snapshot.md](evidence/metrics_snapshot.md) | structured logs, `/api/metrics`, `/health`, `/ready` |
| Streamlit UI for all of the above | Built | frontend tests, Hour 4 live UI check | |

## Resilience and operations

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Background worker with leases, heartbeats, recovery (4.5) | Built | [scenario_A](evidence/scenario_A_worker_crash.md) | |
| Retries with backoff + jitter | Built | [scenario_H](evidence/scenario_H_ambiguous_unavailable.md), [synthetic_load_100.md](evidence/synthetic_load_100.md) | |
| Idempotent run creation | Built | [scenario_C](evidence/scenario_C_duplicates.md) | |
| Cancel | Built | [scenario_I](evidence/scenario_I_cancel.md) | stops at the next check, not mid-call |
| Distributed workers (several processes / machines) | Partial | `tests/test_worker.py` (two concurrent claimers) | design is safe; only one process was run; no shared AI rate limiter |
| Scale: 1,000-row intake | Built | [bulk_intake_1000.md](evidence/bulk_intake_1000.md) | intake only, not crawled |
| Scale: many jobs | Partial | [synthetic_load_100.md](evidence/synthetic_load_100.md) | 100 synthetic jobs with the fake AI; real AI throughput is limited by free tiers |
| Schema migrations, reversible | Built | [scenario_J](evidence/scenario_J_migration.md) | |
| SSRF protection incl. DNS rebinding | Partial | [scenario_D](evidence/scenario_D_ssrf_and_injection.md) | every hop re-checked; no IP pinning |
| Deployment (Supabase + Render) | Partial | [deployment.md](deployment.md), `render.yaml` | files ready; not deployed yet; Docker images never built locally |
| Live URLs | Not built yet | [submission-summary.md](submission-summary.md) | placeholders until deployed |

## Scenarios A-J

| Scenario | Status | Evidence | Data |
|---|---|---|---|
| A - worker crash mid-job | Built | [scenario_A_worker_crash.md](evidence/scenario_A_worker_crash.md) | REAL |
| B - AI provider failure / fallback | Built | [hour2_classifier.md](evidence/hour2_classifier.md), [real_site_pilot.md](evidence/real_site_pilot.md) | REAL |
| C - duplicates | Built | [scenario_C_duplicates.md](evidence/scenario_C_duplicates.md) | REAL |
| D - SSRF and prompt injection | Built | [scenario_D_ssrf_and_injection.md](evidence/scenario_D_ssrf_and_injection.md) | FIXTURE + real AI |
| E - human correction vs new scan | Built | [scenario_E_override_conflict.md](evidence/scenario_E_override_conflict.md) | REAL |
| F - database write failure | Built | [scenario_F_db_write_failure.md](evidence/scenario_F_db_write_failure.md) | TEST |
| G - concurrent edits | Built | [scenario_G_concurrent_edits.md](evidence/scenario_G_concurrent_edits.md) | TEST |
| H - ambiguous evidence vs unavailable site | Built | [scenario_H_ambiguous_unavailable.md](evidence/scenario_H_ambiguous_unavailable.md) | FIXTURE + real AI |
| I - cancel | Built | [scenario_I_cancel.md](evidence/scenario_I_cancel.md) | FIXTURE + fake AI |
| J - migration | Built | [scenario_J_migration.md](evidence/scenario_J_migration.md) | REAL migrations |

**[CHECK the scenario letters and their definitions against the brief; B's definition was not given in a task brief - it is assumed to be "AI provider failure".]**

## Deliverables

| Deliverable | Status | Where |
|---|---|---|
| Source code + tests | Built | repository; 250 backend + 12 frontend tests |
| Design document | Built | [design.md](design.md) |
| API documentation | Built | [api.md](api.md), [openapi.json](openapi.json), live `/docs` |
| Decision log | Built | [decision-log.md](decision-log.md) |
| AI usage statement | Partial | [ai-usage.md](ai-usage.md) | draft, author must confirm |
| Evidence | Built | [evidence/README.md](evidence/README.md) |
| Deployment guide | Built | [deployment.md](deployment.md) |
| Privacy note | Built | [privacy.md](privacy.md) |
| Limitations | Built | [limitations.md](limitations.md) |
| Video walkthrough | Not built yet | [loom-script.md](loom-script.md) (outline only) |
