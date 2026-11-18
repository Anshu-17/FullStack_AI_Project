# Status matrix

Checked against the brief ("24-Hour Full-Stack AI Engineering Challenge", candidate copy), section by section.
The brief itself is not stored in this repository. Status values are the brief's own (section 10):

- **Built and proven** - implemented AND shown by a test or a live run (evidence linked).
- **Built but unverified** - implemented, but not shown end to end (no test / no live run yet).
- **Partial** - implemented with a known gap.
- **Not built** - not implemented.

## 2. Classification semantics

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Seven categories with the brief's definitions / special rules | Built and proven | [real_site_pilot.md](evidence/real_site_pilot.md), `backend/app/classifier/taxonomy.py` | special rules written into the prompt (p3) and keyword checks |
| Accounting = Yes by explicit rule, provenance `rule` | Built and proven | [export_sample.md](evidence/export_sample.md), `tests/test_classify_pipeline.py` | never sent to the AI |
| Yes / Possible / Not Found semantics; Not Found = "not found within the crawl scope" | Built and proven | [scenario_H](evidence/scenario_H_ambiguous_unavailable.md) | failed crawls are "failed", never "not found"; unscanned = "not scanned" |
| Each result records status, explanation, evidence passage, exact URL, date/time, provenance, model + policy version | Built and proven | [export_sample.md](evidence/export_sample.md) | also prompt version |
| Confidence not presented as calibrated | Built and proven | `classifications.confidence`, [limitations.md](limitations.md) | stored, labelled self-reported, not used for decisions |

## 3. Essential workflows

| Workflow | Status | Evidence | Notes |
|---|---|---|---|
| 1. Add one URL or upload CSV; validate, normalise, dedupe, report accepted / rejected rows | Built and proven | [bulk_intake_1000.md](evidence/bulk_intake_1000.md), [scenario_C](evidence/scenario_C_duplicates.md) | |
| 2. Single or batch run; item statuses; inspect successes / failures | Built and proven | [real_site_pilot.md](evidence/real_site_pilot.md), `frontend/tests/test_pages.py::test_run_page_shows_server_progress_and_errors` | |
| 3. Discover relevant pages within crawl and safety limits | Built and proven | crawler tests, [scenario_D](evidence/scenario_D_ssrf_and_injection.md) | |
| 4. Seven categories, traceable evidence, validated, versioned | Built and proven | [real_site_pilot.md](evidence/real_site_pilot.md) | |
| 5. Reviewer corrects with reason; who / what / when kept | Built and proven | [scenario_E](evidence/scenario_E_override_conflict.md), [export_sample.md](evidence/export_sample.md) | append-only, old + new value |
| 6. Later scan never silently overwrites a human override | Built and proven | [scenario_E](evidence/scenario_E_override_conflict.md) | conflict flagged |
| 7. Search / filter, job and quality metrics, download, actionable errors | Built and proven | [metrics_snapshot.md](evidence/metrics_snapshot.md), [export_sample.md](evidence/export_sample.md) | quality metrics = audit + evaluation files, not a live UI chart |
| 8. Retry failed items, stop work, recover interrupted processing without conflicting results | Built and proven | [scenario_A](evidence/scenario_A_worker_crash.md), [scenario_I](evidence/scenario_I_cancel.md), [real_site_pilot.md](evidence/real_site_pilot.md) (manual retry) | |

## 4.1 Frontend

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Loading, empty, failed, completed states | Built and proven | `frontend/tests` (empty state, backend down, run errors, session expired) | |
| Company table, URL / CSV ingest, batch list + detail, search, category filters, evidence viewer, reviewer editing, export | Built and proven | `frontend/tests`, live UI check (decision log) | |
| Progress from server state | Built and proven | `test_run_page_shows_server_progress_and_errors` | refreshes every 3 s |
| Site / rule / human / test-fixture results clearly distinguished | Built and proven | `test_test_data_is_badged_and_can_be_hidden`, `test_detail_shows_evidence_sources_and_conflict` | |
| Visible validation errors, no exposed secrets | Built and proven | `test_login_failure_shows_the_error`, upload rejected-row table | the UI never sees API keys |
| Responsive layout | Built but unverified | - | Streamlit default layout; not checked on a phone |
| Keyboard-usable actions | Built but unverified | - | standard Streamlit widgets; no accessibility audit |

## 4.2 Backend APIs and persistence

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Documented endpoints: ingestion, companies, runs, run items, classifications, evidence, re-analysis, corrections, metrics, exports | Built and proven | [api.md](api.md), [openapi.json](openapi.json) | classifications + evidence are returned by `GET /api/companies/{id}` and the exports (no separate endpoint) |
| Durable persistence: businesses, canonical URLs, pages / evidence, jobs, attempts, decisions, versions, overrides | Built and proven | [design.md](design.md) section 3 | 14 tables |
| Validation, stable ids, pagination, structured responses, actionable errors | Built and proven | `tests/test_api.py`, [api.md](api.md) | |
| Migrations, environment template, seed data | Built and proven | [scenario_J](evidence/scenario_J_migration.md), `backend/.env.example`, `app/db/seed.py` | |
| Authentication + authorisation for modifying operations | Built and proven | `tests/test_auth.py` | reviewer / viewer roles |
| Ownership / tenant boundaries | Not built | - | single organisation by design; no multi-tenant behaviour is claimed |

## 4.3 Discovery, extraction, safe fetching

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Discover internal pages, prioritise relevant ones, normalise / dedupe URLs | Built and proven | `tests/test_crawl.py`, `tests/test_urls.py` | also duplicate-text pages |
| Budgets: depth, pages, total bytes, per-host concurrency, timeouts, retries, job deadline | Built and proven | crawler tests | 2 / 8 / 5 MB / 1 at a time / 120 s per site |
| Redirects, 404 / 429 / 5xx, broken HTML, empty, slow, malformed content | Built and proven | crawler tests, [scenario_H](evidence/scenario_H_ambiguous_unavailable.md) | |
| SSRF: schemes, private / loopback / link-local / metadata blocked, redirects re-checked | Built and proven | [scenario_D](evidence/scenario_D_ssrf_and_injection.md), `tests/test_safety.py` | |
| SSRF: DNS-resolution re-check (rebinding) | Partial | - | each hop resolved and checked, but httpx resolves again on connect; no IP pinning |
| robots.txt respected; no bypassing logins / captchas | Built and proven | crawler tests, pilot (403 sites not bypassed) | |
| No script execution; site text never treated as instructions | Built and proven | [scenario_D](evidence/scenario_D_ssrf_and_injection.md) | |
| JavaScript-rendered sites | Not built | - | not required by the brief; JS-only sites give little text |

## 4.4 AI classification and decision quality

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Reproducible staged pipeline (discovery, selection, classification, validation) | Built and proven | [design.md](design.md) section 6 | plain functions; LangGraph dropped |
| Validated structured output; malformed / incomplete never succeeds | Built and proven | [scenario_B](evidence/scenario_B_ai_failures.md) | |
| Evidence supports its exact category; short excerpts + URLs | Partial | [real_site_pilot.md](evidence/real_site_pilot.md) audit | verbatim + keyword-relevance checks; audit of 78 quotes: 66 OK, 9 weak, 3 questionable |
| Model never overrides the Accounting rule or a human correction | Built and proven | [scenario_E](evidence/scenario_E_override_conflict.md) | |
| Contradictory sources identified; ambiguity -> Possible / review | Partial | [scenario_H](evidence/scenario_H_ambiguous_unavailable.md) | ambiguous / outdated -> `possible` and `review_required`; contradictions between pages are left to the model (prompt rule), no deterministic cross-page check |
| Documented model choice, prompts, preprocessing, retry / fallback, versions, cost controls, failure cases | Built and proven | [design.md](design.md), [decision-log.md](decision-log.md) | cost controls: passage budget, token limit, quota breaker |

## 4.5 Orchestration and recovery

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Job states incl. queued, running, completed, failed, cancelled, review_required; item-level | Built and proven | [design.md](design.md) section 4 | |
| Bounded concurrency, idempotent submission, timeouts, backoff + jitter, retry ceilings, terminal failures visible | Built and proven | [scenario_B](evidence/scenario_B_ai_failures.md), [scenario_C](evidence/scenario_C_duplicates.md), [synthetic_load_100.md](evidence/synthetic_load_100.md) | |
| Orphaned work detected after restart; no duplicate finalised outcomes | Built and proven | [scenario_A](evidence/scenario_A_worker_crash.md) | leases + fencing |
| Partial success, cancellation, manual retry, duplicate submissions | Built and proven | [scenario_I](evidence/scenario_I_cancel.md), [real_site_pilot.md](evidence/real_site_pilot.md), [scenario_C](evidence/scenario_C_duplicates.md) | |
| Multi-worker execution | Partial | `tests/test_worker.py` (two concurrent claimers) | only ONE worker process was run; distributed processing is not claimed; changes needed are in [design.md](design.md) section 10 |

## 4.6 Security, observability, operations

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Secret handling, validation, authorisation, safe URL retrieval, rate limiting | Built and proven | `tests/test_auth.py`, `tests/test_production.py`, [scenario_D](evidence/scenario_D_ssrf_and_injection.md) | rate limits per API process (in memory) |
| Structured logs with correlation / job ids, error categories, attempts, timestamps, no secrets | Built and proven | [scenario_A](evidence/scenario_A_worker_crash.md) log lines | |
| Health / readiness endpoints, migration plan, safe restart | Built and proven | `/health`, `/ready`, [scenario_J](evidence/scenario_J_migration.md), [scenario_A](evidence/scenario_A_worker_crash.md) | |
| Deployment instructions + files | Built and proven | [deployment.md](deployment.md), `render.yaml`, [deployment_smoke_test.md](evidence/deployment_smoke_test.md) | live on Render + Supabase since 2026-11-18; `docker compose` not run locally |
| Metrics: throughput, per-job latency, outcomes, retries | Built and proven | [metrics_snapshot.md](evidence/metrics_snapshot.md) | |
| Metrics: estimated AI usage / cost | Partial | [metrics_snapshot.md](evidence/metrics_snapshot.md) | tokens per call recorded; cost "unknown" because no prices are configured (free tier) - set `AI_PRICE_*` to estimate |
| Privacy / retention boundaries, rules for page excerpts | Built and proven | [privacy.md](privacy.md) | retention is a proposal, not automated |

## 5. Scale, realism, performance

| Test | Status | Evidence | Notes |
|---|---|---|---|
| Bulk intake: 1,000 rows with invalid + duplicate entries, row-level results, no waiting on processing | Built and proven | [bulk_intake_1000.md](evidence/bulk_intake_1000.md) | ~1.4 s; SYNTHETIC rows |
| Real-site pilot: >= 10 public sites end to end, success / failure counts | Built and proven | [real_site_pilot.md](evidence/real_site_pilot.md) | 15 sites: 12 classified, 3 failed (sites refuse crawlers) |
| Controlled workload: >= 100 simulated jobs on local fixtures, disclosed synthetic | Built and proven | [synthetic_load_100.md](evidence/synthetic_load_100.md) | fake AI |
| Recovery: restart worker during in-flight work | Built and proven | [scenario_A](evidence/scenario_A_worker_crash.md) | |
| Search & export of classifications and correction history | Built and proven | [export_sample.md](evidence/export_sample.md) | |
| Quality: labelled fixture set, precision / recall, manual evidence audit | Built and proven | [quality_evaluation.md](evidence/quality_evaluation.md), [real_site_pilot.md](evidence/real_site_pilot.md) | **prompt tuned on the same 9 fixture sites - no held-out set; 54/54 is fit, not accuracy** |
| Latency / cost with environment and sample size | Partial | [synthetic_load_100.md](evidence/synthetic_load_100.md), [metrics_snapshot.md](evidence/metrics_snapshot.md), [scenario_B](evidence/scenario_B_ai_failures.md) | timings and tokens reported; no cost figure |
| 5.1 suggested companies (12) + >= 3 independently selected | Built and proven | `sample-data/real_companies.csv`, [real_site_pilot.md](evidence/real_site_pilot.md) | added: Star Oilco, Kent Nutrition Group, Mozilla (negative control) |

## 6. Adversarial and failure scenarios (A-E demonstrated, F-J tested or design-explained)

| ID | Brief condition | Status | Evidence | Data |
|---|---|---|---|---|
| A | worker crash mid-batch | Built and proven (demonstrated) | [scenario_A_worker_crash.md](evidence/scenario_A_worker_crash.md) | REAL |
| B | AI provider timeout / rate limit / malformed output (retries, then failed - never invented) | Built and proven (demonstrated) | [scenario_B_ai_failures.md](evidence/scenario_B_ai_failures.md) | REAL + TEST (timeout by test only) |
| C | duplicate and concurrent submission | Built and proven (demonstrated) | [scenario_C_duplicates.md](evidence/scenario_C_duplicates.md) | REAL |
| D | malicious site: redirect to private IP (SSRF) + prompt-injection text | Built and proven (demonstrated) | [scenario_D_ssrf_and_injection.md](evidence/scenario_D_ssrf_and_injection.md) | FIXTURE + REAL Gemini |
| E | human override conflicts with a rescan | Built and proven (demonstrated) | [scenario_E_override_conflict.md](evidence/scenario_E_override_conflict.md) | REAL |
| F | transient database failure during a write | Built and proven (tested) | [scenario_F_db_write_failure.md](evidence/scenario_F_db_write_failure.md) | TEST |
| G | concurrent reviewer edits | Built and proven (tested) | [scenario_G_concurrent_edits.md](evidence/scenario_G_concurrent_edits.md) | TEST |
| H | weak / ambiguous / unavailable website evidence | Built and proven (demonstrated) | [scenario_H_ambiguous_unavailable.md](evidence/scenario_H_ambiguous_unavailable.md) | FIXTURE + REAL Gemini |
| I | cancellation during a run | Built and proven (demonstrated) | [scenario_I_cancel.md](evidence/scenario_I_cancel.md) | FIXTURE + fake AI |
| J | schema change / migration with rollback | Built and proven (demonstrated) | [scenario_J_migration.md](evidence/scenario_J_migration.md) | REAL migrations |

## 7. Data model and integration

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Company + canonical identity; incoming records + validation errors | Built and proven | `companies`, `uploads`, `upload_rows` | |
| Batch, job, attempt, state transition, error code, lease / heartbeat | Built and proven | `runs`, `jobs`, `attempts`, `job_events` | |
| Page metadata, original URL, timestamp, extraction outcome, content reference | Built and proven | `pages` | |
| Policy version, model / version / config, classifications, explanations, citations, provenance | Built and proven | `policy_versions`, `runs.config`, `classifications`, `evidence` | |
| Human review: history, actor, timestamp, old / new value, note, conflict state | Built and proven | `overrides`, `classifications.conflicts_with_override` | |
| REST APIs + machine-readable exports | Built and proven | [api.md](api.md), [export_sample.md](evidence/export_sample.md) | |
| Proposed CRM field mapping | Built and proven (document) | [crm-mapping.md](crm-mapping.md) | proposal only |
| Real CRM integration (optional) | Not built | - | not simulated |

## 8-9. Architecture note and AI disclosure

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Component diagram, request-to-result sequence, data model diagram, failure / retry state machine, three key decisions | Built and proven | [design.md](design.md) | Mermaid |
| AI tool inventory, >= 3 concrete examples, verification, limitations | Partial | [ai-usage.md](ai-usage.md) | draft - the author must confirm their own role |

## 10. Mandatory submission package

| # | Artifact | Status | Where / notes |
|---|---|---|---|
| 1 | Live deployed demo + test credentials | Built and proven | UI https://bep-ui-1dt0.onrender.com, API https://bep-api.onrender.com; author's smoke test 2026-11-18 (health, ready, reviewer login, real company run with evidence) + [deployment_smoke_test.md](evidence/deployment_smoke_test.md); credentials shared privately |
| 2 | Repository: source, history, setup, sample `.env`, lockfiles, dependency license notes | Built and proven | `backend/.env.example`, `*/requirements.lock.txt`, [LICENSE](../LICENSE) (MIT, own code), [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) |
| 3 | README / runbook: prerequisites, commands, deploy URLs, env vars, DB setup, worker, migrations, sample input | Built and proven | [README.md](../README.md) |
| 4 | Technical design incl. trust boundaries, security, failure handling, scaling, trade-offs | Built and proven | [design.md](design.md) |
| 5 | API specification with examples, response / error formats, auth | Built and proven | [api.md](api.md), [openapi.json](openapi.json) |
| 6 | Tests / evidence: tests, outcomes, coverage, sample data, failure-injection artifacts, metrics | Built and proven | [evidence/README.md](evidence/README.md), [test_coverage.md](evidence/test_coverage.md) |
| 7 | Development decision log | Built and proven | [decision-log.md](decision-log.md) |
| 8 | AI usage statement | Partial | [ai-usage.md](ai-usage.md) (draft) |
| 9 | Loom video, 20-30 minutes | Not built yet | [loom-script.md](loom-script.md) (outline following the brief's agenda) |
| 10 | Submission summary: one-page status matrix, risks, next three priorities | Built and proven | [submission-summary.md](submission-summary.md) |
