"""FastAPI entry point: logging, request IDs, CORS, one error shape, health/readiness, /api routers.

The API never crawls or calls the AI itself: it stores requests (companies, runs, jobs) and
the background worker (python -m app.worker.main) does the slow work.
"""
import time
import uuid

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api import auth, companies, exports, overrides, runs, stats, uploads
from app.api.errors import register_error_handlers
from app.auth import current_user
from app.config import settings
from app.db.session import engine
from app.log_config import get_logger, setup_logging
from app.ratelimit import limiter, rate_limit_exceeded

setup_logging()
log = get_logger("api")

app = FastAPI(
    title="Business Evidence Platform API",
    version="0.1.0",
    description="Researches company websites and stores evidence-backed business-line classifications.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


register_error_handlers(app)  # {"error": {"code", "message", "details"}} for every error

# Rate limits: per-route limits (login, upload) + a default for every route (see app/ratelimit.py)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)

# Open without login: /health, /ready, /docs, /openapi.json and POST /api/auth/login.
app.include_router(auth.router, prefix="/api")
# Everything else under /api needs a logged-in user (viewer or reviewer). Endpoints that
# CHANGE data additionally depend on require_reviewer.
for router in (uploads.router, companies.router, overrides.router, runs.router, exports.router, stats.router):
    app.include_router(router, prefix="/api", dependencies=[Depends(current_user)])


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Give every request an ID (or reuse the caller's) and log one line per request."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request.unhandled_error", method=request.method, path=request.url.path)
        response = JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR",
                               "message": "Something went wrong on our side. Quote the request ID when reporting it.",
                               "request_id": request_id}},
        )
    response.headers["X-Request-ID"] = request_id
    log.info(
        "request.completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return response


@app.get("/health", tags=["ops"])
def health():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
def ready():
    """Readiness: database reachable and migrations applied. 503 if not ready."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return {"status": "ready", "database": "ok", "migration": revision}
    except Exception as exc:  # report, don't crash
        log.warning("ready.check_failed", error=type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "error", "detail": type(exc).__name__},
        )
