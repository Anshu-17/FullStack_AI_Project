#!/bin/sh
# Container start for a single free Render web service: API + worker in ONE container.
#
# Trade-off (honest): Render's free web services sleep after ~15 minutes without HTTP traffic, and
# background workers are not free. So the worker runs inside the API container and sleeps with it:
# queued jobs only progress while the service is awake (open the UI or call /health to wake it).
# A real production setup runs the API and the worker as SEPARATE always-on services
# (docker-compose.yml does that locally: services "api" and "worker").
set -e

echo "start: applying database migrations"
alembic upgrade head

echo "start: seeding policy and demo users (idempotent; passwords must come from the environment)"
python -m app.db.seed

# Worker in the background, restarted automatically if it ever exits. A crash loses nothing:
# job leases expire and the restarted worker picks the jobs up again.
(
  while true; do
    python -m app.worker.main || true
    echo "start: worker exited, restarting in 5 s"
    sleep 5
  done
) &

echo "start: API on port ${PORT:-8000}"
# exec: uvicorn becomes the main process, so Render's stop signal reaches it directly.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
