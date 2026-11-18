"""GET /stats - live counts for the dashboard. Grows into full metrics in a later stage."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.enums import JobStatus
from app.db.models import Classification, Company, Job, Override, Run

router = APIRouter(tags=["metrics"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Counts straight from the database (no caching, no estimates)."""
    jobs_by_status = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    return {
        "companies": db.scalar(select(func.count()).select_from(Company)),
        "runs": db.scalar(select(func.count()).select_from(Run)),
        "jobs": {status.value: jobs_by_status.get(status.value, 0) for status in JobStatus},
        "classifications": db.scalar(select(func.count()).select_from(Classification)),
        "overrides": db.scalar(select(func.count()).select_from(Override)),
    }
