# Business Evidence Platform

Upload a list of companies; a background worker crawls each company's public website safely, an AI classifies seven
business lines (Accounting, Agronomy, Grain, Energy, Feed, Gas Station, Retail Store), and every answer is backed by a
**verbatim quote from a crawled page** that the system verifies itself. Reviewers see the evidence, correct answers
(the human answer wins, with full history and conflict flags) and export CSV / JSON. Built with Python, FastAPI,
PostgreSQL, a lease-based background worker, Gemini + Groq, and a Streamlit UI.

**Live:** UI https://bep-ui-1dt0.onrender.com · API https://bep-api.onrender.com · API docs
https://bep-api.onrender.com/docs - log in as `reviewer@demo.local` or
`viewer@demo.local` (passwords shared privately). Free hosting sleeps when idle: the first load can take ~1 minute
(see [Getting a 502 error on the live site?](#getting-a-502-error-on-the-live-site) below).

> ### Getting a 502 error on the live site?
>
> The backend runs on Render's **free tier**, which puts the service to sleep after about **15 minutes of
> inactivity**. The next visit has to wake it up, which usually takes **up to a minute**. During that cold start you
> may see a **502 error** when logging in.
>
> **How to fix it:**
>
> 1. Open the backend health check: https://bep-api.onrender.com/health
> 2. Wait until it shows `{"status": "ok"}`.
> 3. Go back to the website and log in again.
>
> The worker runs inside the same backend service, so it can take a little longer for both to be ready after waking
> up. This is a limit of Render's free tier, not a bug in the application. A paid Render plan would remove the
> sleep-related cold starts, and is what I would recommend for a production deployment.

**Video walkthrough (Loom):** https://www.loom.com/share/9a1d51cb8e4e41a08729343b01b293ea ·
**Slides:** [ppt/Business Evidence Platform – Walkthrough.pptx](ppt/Business%20Evidence%20Platform%20%E2%80%93%20Walkthrough.pptx)

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
| `ppt/` | presentation slides (walkthrough deck) |

## Run it yourself (clone and set up)

### Tools you need

| Tool | Version | Why | Get it |
|---|---|---|---|
| Git | any | clone the repository | https://git-scm.com/downloads |
| Python | 3.11 or newer (developed on 3.13) | backend, worker and UI | https://www.python.org/downloads/ |
| PostgreSQL | 16 or newer (developed on 18) | database + job queue | https://www.postgresql.org/download/ (includes `psql` / `createdb`) |
| An AI API key | free tier is enough | the classification step | Gemini: https://aistudio.google.com/apikey · Groq: https://console.groq.com/keys (one is enough; both = fallback) |
| Docker Desktop | optional | run everything with one command instead | https://www.docker.com/products/docker-desktop/ |

Three terminals are used: API, worker, UI. Commands are shown for macOS / Linux (bash); the Windows PowerShell
version is given where it differs.

### 1. Clone

```bash
git clone https://github.com/Anshu-17/FullStack_AI_Project.git
cd FullStack_AI_Project
```

### 2. Create the databases

```bash
createdb -U postgres bep          # the app's database
createdb -U postgres bep_test     # only needed to run the tests
```
(Or in `psql` / pgAdmin: `CREATE DATABASE bep;` and `CREATE DATABASE bep_test;`. On Windows, `createdb` is in
`C:\Program Files\PostgreSQL\<version>\bin` if it is not on your PATH.)

### 3. Backend: install and configure (terminal 1)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate                     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                          # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # copy the output into JWT_SECRET
```

Now open `backend/.env` and fill in the values marked `<FILL IN>` (the file explains each one):

```ini
DATABASE_URL=postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/bep
JWT_SECRET=PASTE_A_LONG_RANDOM_STRING_HERE
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY        # and/or
GROQ_API_KEY=YOUR_GROQ_API_KEY
SEED_REVIEWER_PASSWORD=                   # optional: choose demo passwords, or leave blank to get random ones
SEED_VIEWER_PASSWORD=
```

`.env` is git-ignored: never commit it. Then create the tables and the demo accounts, and start the API:

```bash
alembic upgrade head          # create the tables (repeat after every pull: it only applies new migrations)
python -m app.db.seed         # policy v1 + reviewer@demo.local / viewer@demo.local (prints random passwords ONCE if blank)
uvicorn app.main:app --reload # API on http://localhost:8000 - check http://localhost:8000/ready and /docs
```

### 4. Worker (terminal 2)

The API only stores requests; the worker does the crawling and AI work.

```bash
cd backend
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python -m app.worker.main     # Ctrl+C stops it safely; jobs in progress are picked up again later
```

### 5. UI (terminal 3)

```bash
cd frontend
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py          # http://localhost:8501
```

The UI calls the API at `http://localhost:8000`. If yours runs elsewhere, set `API_URL` first
(`export API_URL=http://host:8000`, PowerShell: `$env:API_URL="http://host:8000"`).

### 6. Try it

1. Open http://localhost:8501 and log in as `reviewer@demo.local` with the password from step 3.
2. **Add companies** -> one website (e.g. `Agtegra Cooperative`, `https://www.agtegra.com`) -> **Start research for
   this company**, or upload `sample-data/real_companies.csv`.
3. **Runs** shows progress (about 30-60 s per company); then **Companies** -> open a company to see the answers and
   their verified quotes. Correct an answer, export CSV.

Without the UI: `python -m app.classifier.cli https://www.example.com --name "Example" --quiet` (in `backend/`,
venv active) crawls and classifies one website and prints the result.

### Troubleshooting

| Problem | Fix |
|---|---|
| `connection refused` / `password authentication failed` | PostgreSQL running? `DATABASE_URL` user, password and database name correct? |
| `/ready` says the database is missing tables | run `alembic upgrade head` in `backend/` |
| UI: "Can't reach the backend" | start the API (step 3) or set `API_URL` |
| Jobs stay `queued` | start the worker (step 4) |
| Jobs fail with `AI_UNAVAILABLE` / `AI_RATE_LIMITED` | check the API keys; free tiers have daily / per-minute limits - wait or add the second provider |
| Forgot the demo passwords | set `SEED_REVIEWER_PASSWORD` in `.env` and run `python -m app.db.seed` again |

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

## Quick start (Docker, alternative to steps 2-5)

```bash
git clone https://github.com/Anshu-17/FullStack_AI_Project.git && cd FullStack_AI_Project
cp backend/.env.example backend/.env       # fill in JWT_SECRET and an AI key (DATABASE_URL is set by compose)
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
cd backend                        # backend venv active
# the tests use a separate database; default postgresql+psycopg://postgres:devpass@localhost:5432/bep_test
export TEST_DATABASE_URL=postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/bep_test
#   PowerShell: $env:TEST_DATABASE_URL="postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/bep_test"
pytest                            # 263 tests (crawling and AI are faked - no network, no AI cost)
ruff check app tests migrations
alembic check                     # models and migrations in sync

cd ../frontend                    # frontend venv active
pytest                            # 22 UI tests (backend faked with respx)
```

The test run wipes and re-creates `bep_test` - never point `TEST_DATABASE_URL` at your real database.

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
| [loom-script.md](docs/loom-script.md) | video walkthrough outline with demo commands ([Loom video](https://www.loom.com/share/9a1d51cb8e4e41a08729343b01b293ea)) |
| [Walkthrough slides](ppt/Business%20Evidence%20Platform%20%E2%80%93%20Walkthrough.pptx) | presentation deck (PowerPoint) |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | license of every pinned dependency (lockfiles: `*/requirements.lock.txt`) |

## Database migrations

```bash
alembic upgrade head                          # apply all
alembic downgrade -1                          # undo the last one
alembic revision --autogenerate -m "message"  # after changing app/db/models.py (review the file!)
alembic check                                 # models and database in sync?
```
