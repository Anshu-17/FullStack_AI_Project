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
