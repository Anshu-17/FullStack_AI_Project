"""FastAPI entry point.

Stage 0: logging, request IDs, CORS, health/readiness.
Routers for companies, runs, etc. are added in later stages.
"""
import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import stats
from app.config import settings
from app.db.session import engine
from app.log_config import get_logger, setup_logging

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


# JSON API routes live under /api (more routers are added stage by stage)
app.include_router(stats.router, prefix="/api")


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
