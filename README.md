# Business Evidence Platform

Upload a list of companies; a background worker crawls each company's public website safely, an AI classifies seven
business lines (Accounting, Agronomy, Grain, Energy, Feed, Gas Station, Retail Store), and every answer is backed by a
**verbatim quote from a crawled page** that the system verifies itself. Reviewers see the evidence, correct answers
(the human answer wins, with full history and conflict flags) and export CSV / JSON. Built with Python, FastAPI,
PostgreSQL, a lease-based background worker, Gemini + Groq, and a Streamlit UI.

**Live:** UI https://bep-ui-1dt0.onrender.com · API https://bep-api.onrender.com · API docs
https://bep-api.onrender.com/docs - log in as `reviewer@demo.local` or
`viewer@demo.local` (passwords shared privately). Free hosting sleeps when idle: the first load can take ~1 minute.

**Start here:** [docs/submission-summary.md](docs/submission-summary.md) (one page) ·
[docs/status-matrix.md](docs/status-matrix.md) (built / partial / not built) ·
[docs/evidence/README.md](docs/evidence/README.md) (proof for every scenario and number).

## Repository layout

| Folder | What's inside |
|---|---|
| `backend/` | FastAPI API, background worker, crawler, classifier, Alembic migrations, tests |
| `frontend/` | Streamlit UI (calls the API over HTTP, never the database) |
| `fixtures/` | local test websites (`fixtures/server.py`, `fixtures/sites/`) |
| `sample-data/` | labelled fixtures, real-pilot company list, generated 1,000-row CSV |
| `scripts/` | evaluation, real-site pilot, load test, bulk CSV generator |
| `docs/` | design, API, decisions, evidence, deployment, privacy, limitations |

## Quick start (local, without Docker)

Prerequisites: Python 3.11+ (developed on 3.13), PostgreSQL 16 or newer (developed on 18), two databases `bep` and
`bep_test`.

```bash
# backend (terminal 1: API)
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                     # set DATABASE_URL, JWT_SECRET, AI keys
alembic upgrade head                                     # create tables
python -m app.db.seed                                    # policy v1 + demo users (prints generated passwords ONCE)
uvicorn app.main:app --reload                            # http://localhost:8000  (docs: /docs)

# worker (terminal 2, same venv, from backend/)
python -m app.worker.main

# UI (terminal 3)
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py                                     # http://localhost:8501 (API_URL if not localhost:8000)
```

### Environment variables (`backend/.env`, template: `backend/.env.example`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (`postgresql+psycopg://...`) |
| `JWT_SECRET` | token signing key (production: random, >= 32 chars) |
| `ENVIRONMENT`, `LOG_LEVEL`, `LOG_JSON`, `CORS_ORIGINS` | runtime mode, logging, allowed UI origin |
| `AI_PROVIDER`, `AI_FALLBACK_PROVIDERS`, `AI_TIMEOUT_SECONDS` | primary / fallback AI provider (`google`, `groq`, ...) |
| `GOOGLE_API_KEY`, `GOOGLE_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL` | provider keys and models (others: `ANTHROPIC_*`, `XAI_*`, `OPENAI_*`, optional) |
| `AI_PRICE_INPUT_PER_MTOK`, `AI_PRICE_OUTPUT_PER_MTOK` | optional prices for cost estimates (blank = cost "unknown") |
| `SEED_REVIEWER_EMAIL` / `_PASSWORD`, `SEED_VIEWER_EMAIL` / `_PASSWORD` | demo accounts created by the seed |
| `CRAWL_ALLOWED_PRIVATE_HOSTS` | TEST ONLY (fixtures); ignored in production |
| `WORKER_CONCURRENCY`, `JOB_LEASE_SECONDS` | worker threads (default 2), lease length (default 120 s) |
| `API_URL` (frontend) | where the UI finds the API (default `http://localhost:8000`) |

Sample input: `sample-data/real_companies.csv` (15 real companies), `sample-data/bulk_1000.csv` (1,000 generated
rows with duplicates and invalid entries), `sample-data/labelled_fixtures.csv` (expected answers for the fixtures).

One website end to end without the API / worker: `python -m app.classifier.cli https://www.example.com --name "Example" --quiet`
(in `backend/`).

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env       # edit values
docker compose up --build                   # Postgres + API (runs migrations) + worker + UI
docker compose exec api python -m app.db.seed
```

UI http://localhost:8501 · API http://localhost:8000/docs. (The Dockerfiles are built and running on Render; the
compose file itself has not been run, as Docker is not installed on the development machine.)

## Deploy

Supabase (Postgres) + Render (two free Docker web services, Blueprint `render.yaml`):
[docs/deployment.md](docs/deployment.md).

## Tests

```bash
cd backend
pytest                            # 250 tests against the bep_test database (TEST_DATABASE_URL)
ruff check app tests migrations
alembic check                     # models and migrations in sync

cd ../frontend
pytest                            # 12 UI tests (backend faked with respx)
```

Local fixture websites for controlled demos: `python fixtures/server.py`, then start the worker with the TEST-ONLY
settings `CRAWL_FIXTURE_SERVER=127.0.0.1:8765 CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test` (command environment only;
ignored in production). `AI_PROVIDER=fake` gives a deterministic keyword "AI" for load tests (refused in production).

## Documentation

| Document | Contents |
|---|---|
| [submission-summary.md](docs/submission-summary.md) | one-page overview, live links, key numbers |
| [design.md](docs/design.md) | architecture, sequence, ERD, state diagrams, retries / leases, AI pipeline, security, observability, decisions, scale path |
| [api.md](docs/api.md) · [openapi.json](docs/openapi.json) | endpoints, roles, auth, error / list shapes, idempotency, examples |
| [status-matrix.md](docs/status-matrix.md) | every requirement and scenario A-J: built / partial / not built + evidence |
| [evidence/README.md](docs/evidence/README.md) | index of all evidence files (real vs fixture vs synthetic) |
| [decision-log.md](docs/decision-log.md) | chronological decisions and trade-offs |
| [ai-usage.md](docs/ai-usage.md) | how AI tools were used and reviewed (draft) |
| [limitations.md](docs/limitations.md) | known limitations and next steps |
| [privacy.md](docs/privacy.md) | what is stored, retention, AI provider data |
| [crm-mapping.md](docs/crm-mapping.md) | proposed CRM field mapping (not built) |
| [deployment.md](docs/deployment.md) | Supabase + Render step by step |
| [loom-script.md](docs/loom-script.md) | video walkthrough outline with demo commands |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | license of every pinned dependency (lockfiles: `*/requirements.lock.txt`) |

## Database migrations

```bash
alembic upgrade head                          # apply all
alembic downgrade -1                          # undo the last one
alembic revision --autogenerate -m "message"  # after changing app/db/models.py (review the file!)
alembic check                                 # models and database in sync?
```
