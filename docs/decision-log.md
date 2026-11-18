# Decision Log

## 2026-11-17 — Setup

**Stack**

| Choice | Reason |
|---|---|
| PostgreSQL (16+; 18 locally, Supabase for deployment) | Reliable relational store for companies, pages, evidence and reviews; Supabase is managed Postgres, so nothing changes at deploy time. |
| FastAPI | Typed, fast Python API with automatic `/docs` and Pydantic validation. |
| Separate background worker | Crawling and AI calls are slow; running them outside the API keeps requests fast and lets jobs resume after a crash. |
| SQLAlchemy + Alembic + psycopg 3 | Standard Python ORM, versioned migrations with downgrade, modern Postgres driver. |
| httpx + BeautifulSoup + lxml | Page downloads with timeouts/limits; robust HTML text and link extraction. |
| LangGraph (+ Postgres checkpointer) | Staged crawl → select → classify → validate pipeline whose progress is saved in Postgres. |
| LangChain connectors for Anthropic, Google, xAI | One interface for several AI providers, enabling a configurable primary provider plus fallbacks. |
| tenacity, structlog, PyJWT, bcrypt, slowapi | Retries with backoff, structured JSON logs, login tokens, password hashing, rate limiting. |
| Streamlit frontend | I'm fluent in Python, so Streamlit is the fastest way to build the UI in 24 hours. It is a separate service that calls the FastAPI backend over HTTP and **never** connects to the database directly. |
| No React / Node.js | Keeps the whole project in one language and one toolchain. |

**Versions**

Versions are pinned in `requirements.txt` (direct dependencies) and `requirements.lock.txt` (full resolved set, generated with `pip-compile`), separately for `backend/` and `frontend/`. Each service has its own virtual environment.

## Stage 0 - Foundation

- **Stack:** Python 3.13 + FastAPI, PostgreSQL 16, SQLAlchemy 2 + Alembic, LangGraph (Claude / Gemini / Grok), React + Vite, Docker Compose for local dev.
- **One repository** (backend, frontend, fixtures, docs) so the evaluator can trace everything from one place.
- **One backend image, two roles:** the same Docker image runs the API (`uvicorn`) and the worker (`python -m app.worker.main`). Keeps code shared and lets us kill/restart the worker alone for the recovery demo.
- **Structured JSON logs** (structlog). Every request gets an `X-Request-ID` (reused if the caller sends one) that appears on every log line for that request.
- **Health vs readiness:** `/health` never touches the DB (is the process alive?); `/ready` checks the DB and reports the applied migration, returning **503** when not ready.
- **Requirements:** `requirements.txt` is the short, commented list of direct dependencies; `requirements.lock.txt` (pip-compile) pins everything for reproducible Docker builds. Test tools are in `requirements-dev.txt` and not shipped in the image.
- Renamed `app/logging.py` to `app/log_config.py` to avoid confusion with Python's built-in `logging` module.

## Stage 1 - Database

- **14 tables** covering intake -> work -> findings -> human review (see `backend/app/db/models.py`).
- **Integrity in the database, not just in code.** Unique constraints make these impossible even under races:
  - same website twice (`companies.canonical_domain`)
  - two jobs for one company in one run (`jobs (run_id, company_id)`)
  - two answers for one category in one job (`classifications (job_id, category)`)
  - two runs from one double-click (`runs.idempotency_key`)
  - two reviewers saving the same override version (`overrides (company_id, category, version)`) - optimistic locking
- **Statuses as strings + CHECK constraints** instead of Postgres ENUM types: easier to add values in a later migration.
- **Overrides are append-only.** The current human answer is the highest version; nothing is updated or deleted, so the full audit history is kept. `new_status = NULL` means "override removed".
- **Leases on jobs** (`lease_owner`, `lease_expires_at`, `heartbeat_at`) plus `next_attempt_at` for backoff. Partial index on running jobs' lease expiry for fast crash recovery.
- **Confidence** column documented as model self-reported, *not* a calibrated probability.
- **Pages store cleaned text (size-capped), not raw HTML**, plus a content hash. Evidence stores a short quote and a `quote_verified` flag.
- **LangGraph checkpoint tables** are created by LangGraph itself; excluded from Alembic autogenerate.
- **Seed script** creates policy `v1` and two demo users. Passwords come from `.env`, or are randomly generated and printed once - no credentials in the repo.
- **Verified:** migration upgrade -> downgrade -> upgrade on real Postgres 16; `alembic check` reports no drift; 16 tests pass (constraint tests, health/ready, password hashing).
- **Environment note:** Docker daemon was not available in the AI-assisted build environment, so `docker-compose.yml` was written but tested only by running Postgres 16, the API and the worker directly. To verify on a machine with Docker.

## Frontend decision (superseded - see final decision below)

- Considered Streamlit, NiceGUI, Jinja2 + HTMX and React. Briefly started Streamlit and Jinja2 set-ups, then removed them.
- **Chosen: simple React** (plain JavaScript, no TypeScript, no state or UI libraries; `fetch` + `useState`/`useEffect`, React Router, Pico.css).
- **Served by FastAPI:** `npm run build` outputs static files that FastAPI serves at `/`; the JSON API lives under `/api/...`. One address and one deployment, so no CORS set-up, and login uses a secure HttpOnly cookie that the browser sends automatically (the React code never stores tokens).
- **Why React over HTMX:** a clean "frontend calls the backend API" boundary and a smoother UI, at a cost of roughly 2-3 extra hours. Kept deliberately minimal so every file can be explained.
- `jinja2` removed from the Python requirements (not needed to serve built files).

## Final stack decision

- **Constraint:** about 13 hours left (7 for coding with AI, 6 for docs, demo and video). I am fluent in Python, not in JavaScript, and must explain every file in the live defence.
- Compared our Python plan with an alternative Nuxt/TypeScript plan. Same architecture and requirement analysis; the difference was language. Kept Python because Stages 0-1 were already built and tested, and the alternative's Supabase-JS data access lacked transactions for safe job claiming and all-or-nothing saves.
- **Frontend: Streamlit**, a separate Python service that calls the FastAPI backend over HTTP (`API_URL`). It never connects to the database. Pure Python, with tables, upload, download and auto-refresh built in.
- React removed (not familiar enough to defend in the time available).
- **Trade-offs accepted:** less layout flexibility than React; the page script re-runs on each interaction; suited to a small team of reviewers rather than many concurrent users. A JavaScript frontend could replace it later on the same API.
- Backend requirements unchanged. Frontend has its own `requirements.txt` (streamlit, httpx) and lockfile.
- **Verified:** real FastAPI + real Streamlit run together; dashboard shows live database counts via `GET /api/stats`; UI tests cover the "backend down" message. 17 backend + 2 frontend tests pass.

## Hour 1 - Crawler

- **Design:** plain functions in `backend/app/crawler/` - `safety` (SSRF), `urls` (normalisation), `robots`, `fetch` (one page), `extract` (HTML -> text + links), `crawl` (one site), `store` (save pages). Not an API endpoint; the worker will call it. It only *collects* pages and never classifies. Page text is untrusted data and is only stored (tested with an "IGNORE ALL PREVIOUS INSTRUCTIONS..." page).
- **Limits (per website):** 8 pages, depth 2, 10 s per network operation (and per body read), 1.5 MB per page, 5 MB total, 5 redirects, 120 s deadline. Whichever is hit first is reported as `stopped_reason`. 8 pages is enough for the homepage plus the product/service/location pages that carry evidence, and keeps a 100-company run fast and cheap. Pages are fetched one at a time per site (polite); parallelism across companies is the worker's job.
- **Page priority:** a priority queue - links whose path or link text mentions our business lines (grain, agronomy, propane, feed, locations, ...) first, blog/news/careers/login/privacy last, breadth-first within a priority. Because we only take 8 pages, they should be the most useful 8.
- **robots.txt (RFC 9309):** 4xx -> allow all; 5xx, 429, timeout or unreachable -> disallow all; cached per origin for the crawl. Parsed with `urllib.robotparser` (limitation: no `*`/`$` wildcards, first-match not longest-match). Disallowed pages are recorded as `robots_disallowed`, never fetched.
- **SSRF protection:** only http/https, no `user:pass@`, and *every* IP the hostname resolves to must be public (`is_global`, IPv4-mapped IPv6 unwrapped) - blocks 127.x, 10.x, 172.16-31.x, 192.168.x, 169.254.169.254, ::1. Redirects are followed by hand and every hop is re-checked. `CRAWL_ALLOWED_PRIVATE_HOSTS` allows local test fixtures and is ignored in production. **Known limitation - DNS rebinding:** we resolve, then httpx resolves again when connecting; re-checking every hop narrows the window, full IP pinning is future work.
- **Fetch robustness:** never raises - every problem becomes a `PageOutcome`. 4xx is final; 429/5xx/timeouts are retried twice with exponential backoff + jitter, honouring `Retry-After` up to a 4 s cap. Bodies are streamed and cut off at the size limit (the declared `Content-Length` is not trusted). Only `text/html` is accepted.
- **No JavaScript rendering (limitation):** we read the HTML the server sends. Sites that build their content in the browser will return little text; those pages show up with short text and can be flagged for review. A headless browser was rejected as too heavy and too risky for this time box.
- **Storage:** cleaned text only (max 50,000 chars per page; block elements become lines, inline whitespace collapses so quotes can be matched later), plus a SHA-256 of the text. `(job_id, url)` stays unique: a retried job *updates* its page rows (Postgres upsert) instead of duplicating them. NUL characters are stripped (Postgres rejects them).
- **Verified:** 112 backend tests pass (17 existing + 95 new: urls 32, safety 19, fetch 16, crawl 12, robots 6, extract 6, store 4); HTTP faked with respx, DNS faked - no real network in tests. Real-site check with the CLI: agtegra.com 8/8 pages ok (products-services, agronomy, energy, feed, grain, locations; 20 s), insightfs.com 8/8 ok (3 s).
- **Observed on real sites (follow-ups):** (1) insightfs.com redirects to `fscooperatives.com/insightfs`, a shared site for several FS co-ops; the crawler then treats the whole `fscooperatives.com` as the company site, so pages of *other* co-ops could be collected. Fix candidate: after a cross-domain homepage redirect, stay under the redirect's path prefix. (2) Navigation menus repeat at the top of every page's text; removing `<nav>/<header>/<footer>` would give cleaner evidence.

## Hour 2 - Classifier

- **Crawler follow-ups fixed first:** (1) after a cross-domain homepage redirect (insightfs.com -> fscooperatives.com/insightfs) the crawler stays under the target path and records `redirected_to`; sibling paths of a shared site are never crawled. (2) `<nav>` and `<header>` are removed from page text (menu noise) while their links are still followed; `<footer>` is kept because addresses and opening hours are retail-store evidence.
- **LangGraph dropped:** the pipeline is plain staged Python functions (select -> prompt -> call -> validate -> save). Simpler to read and explain, and still a reproducible staged pipeline: versioned prompt and policy, deterministic passage selection, every AI call logged. `langgraph` and `langgraph-checkpoint-postgres` removed from requirements; `langchain-openai` added (Groq).
- **Providers:** Gemini (`gemini-2.5-flash`) primary, Groq (`openai/gpt-oss-20b`) fallback through Groq's OpenAI-compatible API, so no extra package. Anthropic/xAI/OpenAI are wired but unused. A provider is used only if both its key and model are set. Temperature 0; each client's own retries are disabled so every attempt is ours and visible in `ai_usage`.
- **Passage budget:** pages are split into ~400-character passages, scored per category by keyword hits; the homepage's first passage plus the top 5 per category (round-robin) are sent, capped at 12,000 characters (~3-4k input tokens). Controls cost and free-tier rate limits; deterministic, so a run is reproducible.
- **Prompt security:** website text is untrusted. It is sent only inside `<untrusted_website_content>` tags in the user message (a page cannot close the tag early - it is neutralised), and the system prompt says to treat it as data. We do not rely on the model obeying: validation below is what protects the result.
- **Validation (trust nothing from the model):** all 6 site categories exactly once (else retry); every quote must be verbatim in the cited passage AND in the stored page text (whitespace/case-insensitive) or it is dropped; `yes`/`possible` with no verified quote becomes `not_found`; a `yes` whose quotes contain none of the category's keywords becomes `possible` (simple relevance heuristic); any downgrade, dropped quote, `possible` or override conflict sets `review_required`. Accounting is never sent to the AI: `yes` by business rule, provenance `rule`.
- **Size limits enforced per quote, not per answer:** on a real run, one 370-character quote made Gemini's otherwise good answer fail the schema three times. Limits (quote 10-300 chars, max 3 quotes, explanation 400 chars) are now told to the model and enforced in validation per item; wrong categories/statuses still reject the answer.
- **Prompt p2:** real runs showed models stitching separate fragments into one "quote" (with "..." or skipped words). The prompt now requires one continuous span; stitched quotes are still caught and dropped by validation.
- **Retry / fallback:** per provider up to 3 attempts with exponential backoff + jitter (tenacity), honouring Retry-After / Gemini's "retry in Ns" up to 10 s, for timeouts, 429, 5xx and invalid output. A bad key (`AI_AUTH`) or unknown model (404) is not retried - straight to the next provider. All providers failing -> `AI_UNAVAILABLE`, no classifications saved. No usable crawled text -> `NO_CONTENT` (a crawl failure, not "not found" x6), no AI call.
- **Human overrides:** the latest override per category (highest version, non-removed) is compared with the new automated status; a difference sets `conflicts_with_override` and review. Override rows are never changed.
- **Cost recording:** tokens and latency for every call in `ai_usage`; `est_cost_usd` only when prices are configured (`AI_PRICE_*_PER_MTOK`), otherwise NULL ("unknown") - never invented. One price pair applies to all providers (simplification).
- **Data note:** Gemini's free tier may use requests to improve Google's products. We only send public website text (no personal or customer data).
- **Verified:** 148 backend tests pass (fake chat model, no network); real runs on agtegra.com: Gemini primary - all 6 site categories `yes` with verified quotes (cardlock fuel stations, farm stores, feed, propane, cash bids); forced fallback (`GOOGLE_MODEL=does-not-exist` for one command) - one `AI_ERROR` row for Google, then Groq `ok`.
- **Known limitations:** keyword relevance check is a heuristic (word-start matching; can be fooled or be too strict); confidence is model self-reported; quotes spanning two passages cannot verify; classifications for a job cannot be saved twice (unique per job/category) - the worker must not re-classify a finished job; Gemini 2.5 Flash "thinking" tokens are counted as output tokens.
