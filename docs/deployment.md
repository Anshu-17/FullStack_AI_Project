# Deployment: Supabase (database) + Render (API + UI)

Free tiers only. Two Render web services built from this repository's Dockerfiles:

| Service | Folder | What runs in it | Public URL (if the name is free) |
|---|---|---|---|
| `bep-api` | `backend/` | `start.sh`: migrations -> seed -> worker (background, auto-restart) -> API on `$PORT` | `https://bep-api.onrender.com` |
| `bep-ui` | `frontend/` | Streamlit on `$PORT`, calls the API over HTTPS (never the database) | `https://bep-ui.onrender.com` |

> **Honest trade-off.** Render background workers are not free and free web services sleep after ~15 minutes
> without traffic, so the worker runs INSIDE the API container and sleeps with it. Jobs only progress while
> `bep-api` is awake (keep the UI open or call `/health`). A real deployment runs the API and the worker as
> two separate always-on services (as `docker-compose.yml` does locally).

## 1. Supabase - create the database

1. https://supabase.com -> **New project**. Choose a strong database password (save it in your password
   manager) and a region close to the Render region in `render.yaml` (default `frankfurt` - change both if needed).
2. Wait until the project is ready.
3. Click **Connect** (top of the project page) -> **Connection string** -> choose **Session pooler**.
   - Use the **session pooler** (port **5432**, host like `aws-0-<region>.pooler.supabase.com`, user
     `postgres.<project-ref>`). It works from Render (IPv4) and supports everything the app uses.
   - Do **not** use the *transaction* pooler (port 6543): it breaks session features. (The app also turns off
     psycopg's prepared statements for pooler hosts as a safety net.)
   - The *direct* connection (`db.<ref>.supabase.co`) is IPv6-only on the free plan and may not be reachable from
     Render.
4. Copy the string and replace `[YOUR-PASSWORD]` with your database password. It looks like
   `postgresql://postgres.abcdefgh:<password>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres`
   - You can paste it exactly like that: the app turns `postgresql://` into `postgresql+psycopg://` and adds
     `sslmode=require` for Supabase hosts automatically. (Writing `postgresql+psycopg://...?sslmode=require`
     yourself is also fine.)
   - If the password contains special characters (`@ : / ? # %`), URL-encode them (e.g. `@` -> `%40`).
5. Nothing else to do in Supabase: the API creates the tables itself on first start (`alembic upgrade head`).

## 2. Render - create the services from the Blueprint

1. https://render.com -> sign in with GitHub -> **New +** -> **Blueprint**.
2. Connect the repository `Anshu-17/FullStack_AI_Project`, branch `main`. Render finds `render.yaml`.
3. Render lists the two services and asks for every `sync: false` value of **bep-api**:

| Variable | What to enter |
|---|---|
| `DATABASE_URL` | the Supabase **session pooler** string from step 1.4 |
| `JWT_SECRET` | a new random string: run `python -c "import secrets; print(secrets.token_urlsafe(48))"` (>= 32 characters - the API refuses to start otherwise) |
| `GOOGLE_API_KEY` | your Gemini key (Google AI Studio) |
| `GROQ_API_KEY` | your Groq key |
| `SEED_REVIEWER_PASSWORD` | choose a password for `reviewer@demo.local` (required in production) |
| `SEED_VIEWER_PASSWORD` | choose a password for `viewer@demo.local` (required in production) |

   Plain values (already in `render.yaml`, change in the dashboard if needed): `ENVIRONMENT=production`,
   `AI_PROVIDER=google`, `AI_FALLBACK_PROVIDERS=groq`, `GOOGLE_MODEL=gemini-2.5-flash`,
   `GROQ_MODEL=openai/gpt-oss-120b`, `WORKER_CONCURRENCY=1`, `LOG_JSON=true`, `LOG_LEVEL=INFO`,
   `CORS_ORIGINS=https://bep-ui.onrender.com`, `SEED_REVIEWER_EMAIL`, `SEED_VIEWER_EMAIL`; and for **bep-ui**:
   `API_URL=https://bep-api.onrender.com`.
4. Click **Apply**. Render builds both images (first build ~5-10 minutes).

## 3. Deploy order and URLs

1. **bep-api first.** Wait until its status is **Live**. Its logs should show:
   `start: applying database migrations` -> Alembic upgrades -> `policy v1 created` / `user ... created` ->
   `worker.started` -> `Uvicorn running`.
2. Note the API's real URL (dashboard, top of the service). If it is NOT `https://bep-api.onrender.com`
   (name taken), open **bep-ui -> Environment**, set `API_URL` to the real API URL, and **save** (redeploys the UI).
   Likewise set `CORS_ORIGINS` on bep-api to the UI's real URL.
3. **bep-ui**: wait until Live.

## 4. Check it works

| Check | URL | Expected |
|---|---|---|
| process up | `https://bep-api.onrender.com/health` | `{"status": "ok"}` |
| database + migrations | `https://bep-api.onrender.com/ready` | `{"status": "ready", "database": "ok", "migration": "13822ee21a66"}` |
| API docs | `https://bep-api.onrender.com/docs` | Swagger page |
| UI | `https://bep-ui.onrender.com` | login page |
| UI health | `https://bep-ui.onrender.com/_stcore/health` | `ok` |

The first request after a sleep takes ~1 minute (cold start) - wait and reload.

**Log in** on the UI with `reviewer@demo.local` and the `SEED_REVIEWER_PASSWORD` you chose (or `viewer@demo.local`).

**Smoke test (2-3 minutes):**
1. As reviewer: **Add companies** -> one website, e.g. name `Agtegra Cooperative`, website `https://www.agtegra.com`.
2. **Companies** -> open it -> **Rescan this company** (or start research from the upload).
3. **Runs** -> the run shows `running`, refreshing every 3 s, then `completed` / `review_required` (~1 min).
4. **Company detail** -> 7 answers with quotes and source links. **Dashboard** -> AI calls and tokens.
5. Log out, log in as viewer -> the same data is visible, no edit buttons.

## 5. Logs, redeploys, changes

- **Logs:** Render dashboard -> service -> **Logs** (JSON lines; search for `"job_id": 12`, `ai.call_failed`,
  `job.lease_recovered`, `ai.quota_cooldown_started`).
- **Redeploy:** every push to `main` redeploys both services (`autoDeploy: true`), or **Manual Deploy -> Deploy
  latest commit**. Migrations run automatically on every start (safe to repeat).
- **Change a setting / secret:** service -> **Environment** -> edit -> **Save changes** (restarts the service).
- **Database:** Supabase -> **Table Editor** / **SQL Editor** to look at `jobs`, `classifications`, `ai_usage`.

## 6. Known free-tier limits

| Limit | Effect | What to do |
|---|---|---|
| Free web services sleep after ~15 min idle | first request ~1 min (cold start); the worker sleeps too, queued jobs wait | open the UI / call `/health` before a demo; keep the UI open while a run is processing |
| ~512 MB memory per free service | API + worker share it; `WORKER_CONCURRENCY=1` keeps memory low | don't raise concurrency on the free plan |
| Gemini free tier: 20 requests per model per day | after that the provider is skipped for 30 min and Groq is used | keep demos small; a paid key removes the limit |
| Groq free tier: per-minute limits | big batches get `AI_RATE_LIMITED`, then backoff / retry | small batches; "Retry failed" afterwards |
| Supabase free: project pauses after 7 days without activity | `/ready` -> 503 until it is restored | open the Supabase dashboard and restore the project |
| Some company websites block crawlers (403) | job `failed` with `NO_CONTENT` | expected; research those manually |

## 7. Local equivalent

`docker compose up --build` runs the same images locally with a local Postgres (the API and the worker as
separate services). Note: the Docker images were not built on the development machine (Docker is not installed
there); the first real build is Render's.
