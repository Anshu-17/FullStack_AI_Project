# Business Evidence Platform

Researches public company websites, classifies business lines (Accounting, Agronomy, Grain, Energy, Feed, Gas Station, Retail Store) with evidence, and lets reviewers correct the results.

> Status: work in progress. Stages 0-1 (foundation + database) complete. See `docs/decision-log.md`.

## Repository layout

| Folder | What's inside |
|---|---|
| `backend/` | FastAPI API, background worker, crawler, LangGraph classifier, Alembic migrations, tests |
| `frontend/` | Streamlit UI (calls the FastAPI backend over HTTP) |
| `fixtures/` | Local fake websites for controlled tests |
| `sample-data/` | Input CSVs |
| `docs/` | Design, decision log, AI usage, test evidence |

## Run locally with Docker

```bash
cp backend/.env.example backend/.env      # then edit values
docker compose up --build                  # Postgres + API (runs migrations) + worker + UI
docker compose exec api python -m app.db.seed   # demo users + policy v1
```

- UI: http://localhost:8501
- API: http://localhost:8000 · API docs: http://localhost:8000/docs
- Health: `/health` (process up) · Readiness: `/ready` (database + migration)

## Run locally without Docker

Prerequisites: Python 3.11+, PostgreSQL 16 or newer (developed on 18 locally).

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                    # set DATABASE_URL etc.
alembic upgrade head                                    # create tables
python -m app.db.seed                                   # demo users + policy v1
uvicorn app.main:app --reload                           # API on :8000
python -m app.worker.main                               # worker (second terminal)
```

Frontend (third terminal):

```bash
cd frontend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py                                    # http://localhost:8501
```
Set `API_URL` if the backend is not on `http://localhost:8000`.

## Logging in

Everything except `/health`, `/ready` and the API docs needs a login.

- `python -m app.db.seed` (in `backend/`) creates two demo accounts:
  - `reviewer@demo.local` - can add companies, start / cancel / retry runs and correct answers
  - `viewer@demo.local` - can read everything and export
- Passwords: set `SEED_REVIEWER_PASSWORD` / `SEED_VIEWER_PASSWORD` in `backend/.env` before seeding, or leave
  them blank and the seed prints random ones **once**. They are shared privately, never committed.
- Streamlit (http://localhost:8501) shows a login page; the API docs (http://localhost:8000/docs) have an
  "Authorize" button - get a token with `POST /api/auth/login`.
- In production (`ENVIRONMENT=production`) the API refuses to start unless `JWT_SECRET` is a random string of at
  least 32 characters.

## Background worker

The API only stores requests; the worker does the crawling and AI work. Start it in its own terminal
(backend venv active, from `backend/`):

```bash
python -m app.worker.main
```

- Runs `WORKER_CONCURRENCY` jobs in parallel (default 2) and logs JSON lines with `worker_id`, `job_id`, `run_id`, `attempt`.
- Ctrl+C stops claiming new jobs and waits up to 30 s for jobs in progress.
- Safe to kill at any time: the job's lease (`JOB_LEASE_SECONDS`, default 120) expires and the job is picked up again.
- Start research with `POST /api/runs` (see http://localhost:8000/docs), e.g.
  `{"company_ids": [1, 2]}` with an `Idempotency-Key` header, then watch `GET /api/runs/{id}`.

Short lease for a crash demo, for one command only (`.env` unchanged):

```bash
JOB_LEASE_SECONDS=30 python -m app.worker.main                    # macOS / Linux
```
```powershell
$env:JOB_LEASE_SECONDS=30; python -m app.worker.main               # Windows PowerShell (this window only)
```

Try one website end to end without the worker or API (creates a run + job, prints the answers):

```bash
python -m app.classifier.cli https://www.example.com --name "Example Co-op" --quiet
```

Evidence of the resilience scenarios: `docs/evidence/` (worker crash, duplicates, classifier runs).

## Tests

```bash
cd backend
createdb bep_test                 # one-time: separate test database
pytest                            # set TEST_DATABASE_URL to use another database
ruff check app tests migrations   # lint

cd ../frontend && pytest          # UI tests (backend faked with respx)
```

## Database migrations

```bash
alembic upgrade head                          # apply all
alembic downgrade -1                          # undo the last one
alembic revision --autogenerate -m "message"  # after changing app/db/models.py (review the file!)
alembic check                                 # models and database in sync?
```
