"""GET /stats (dashboard counts) and GET /metrics (operations: retries, durations, AI usage and cost).

Every number is computed from the database on request - nothing is cached or estimated.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.enums import JobStatus
from app.db.models import AIUsage, Classification, Company, Job, Override, Run

router = APIRouter(tags=["metrics"])


def _jobs_by_status(db) -> dict[str, int]:
    counts = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    return {status.value: counts.get(status.value, 0) for status in JobStatus}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Counts straight from the database (no caching, no estimates)."""
    return {
        "companies": db.scalar(select(func.count()).select_from(Company)),
        "runs": db.scalar(select(func.count()).select_from(Run)),
        "jobs": _jobs_by_status(db),
        "classifications": db.scalar(select(func.count()).select_from(Classification)),
        "overrides": db.scalar(select(func.count()).select_from(Override)),
    }


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    # Duration of finished, successful jobs: from first claim to finish (includes any retry waits).
    seconds = extract("epoch", Job.finished_at - Job.started_at)
    finished_ok = Job.status.in_([JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED])
    avg_s, median_s = db.execute(
        select(func.avg(seconds), func.percentile_cont(0.5).within_group(seconds))
        .where(finished_ok, Job.started_at.is_not(None), Job.finished_at.is_not(None))
    ).one()

    ai_rows = db.execute(select(AIUsage.provider, AIUsage.outcome, func.count())
                         .group_by(AIUsage.provider, AIUsage.outcome).order_by(AIUsage.provider)).all()
    calls: dict[str, dict[str, int]] = {}
    for provider, outcome, n in ai_rows:
        calls.setdefault(provider, {})[outcome] = n

    tokens_in, tokens_out, known_cost, calls_without_cost = db.execute(select(
        func.coalesce(func.sum(AIUsage.input_tokens), 0), func.coalesce(func.sum(AIUsage.output_tokens), 0),
        func.sum(AIUsage.est_cost_usd), func.count().filter(AIUsage.est_cost_usd.is_(None)))).one()

    return {
        **stats(db),
        "retries": db.scalar(select(func.coalesce(func.sum(func.greatest(Job.attempt_count - 1, 0)), 0))),
        "job_duration_seconds": {"avg": round(float(avg_s), 1) if avg_s is not None else None,
                                 "median": round(float(median_s), 1) if median_s is not None else None},
        "ai_calls": calls,
        "ai_tokens": {"input": int(tokens_in), "output": int(tokens_out)},
        # None = no prices configured (free tier / unknown); never an invented number.
        "est_cost_usd": float(known_cost) if known_cost is not None else None,
        "ai_calls_without_cost": calls_without_cost,
    }
