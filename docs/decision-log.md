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
