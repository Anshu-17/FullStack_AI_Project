"""Runs and jobs: start, watch, cancel, retry. Progress always comes from the database."""
from fastapi import APIRouter, Depends, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import not_found
from app.auth import require_reviewer
from app.db.deps import get_db
from app.db.enums import JOB_TERMINAL, JobStatus
from app.db.models import Attempt, Classification, Company, Job, JobEvent, Page, Run, User
from app.schemas.common import PageParams, page_params, paginate
from app.services.runs import cancel_run, company_ids_for_request, create_run, job_counts, retry_failed, retry_job

router = APIRouter(tags=["runs"])


class RunIn(BaseModel):
    """Exactly one of: company_ids, upload_id, all_companies."""

    company_ids: list[int] | None = None
    upload_id: int | None = None
    all_companies: bool = False

    @model_validator(mode="after")
    def exactly_one_source(self):
        given = sum([self.company_ids is not None, self.upload_id is not None, self.all_companies])
        if given != 1:
            raise ValueError("give exactly one of company_ids, upload_id or all_companies")
        return self


def run_created_response(run: Run, created: bool, skipped: list) -> JSONResponse:
    """201 for a new run; 200 when the Idempotency-Key matched an earlier run (nothing new created)."""
    body = {"run_id": run.id, "status": run.status, "total_items": run.total_items, "skipped": skipped,
            "created": created}
    return JSONResponse(status_code=201 if created else 200, content=jsonable_encoder(body))


def run_json(run: Run, counts: dict[str, int]) -> dict:
    total = sum(counts.values())
    done = sum(counts[str(s)] for s in JOB_TERMINAL)
    return {
        "id": run.id, "status": run.status, "total_items": run.total_items, "policy_version": run.policy_version,
        "idempotency_key": run.idempotency_key, "created_at": run.created_at, "started_at": run.started_at,
        "finished_at": run.finished_at, "cancel_requested_at": run.cancel_requested_at,
        "skipped": (run.config or {}).get("skipped", []),
        "counts": counts,
        "progress": {"done": done, "total": total, "percent": round(100 * done / total, 1) if total else 0.0},
    }


def item_json(job: Job) -> dict:
    return {"job_id": job.id, "company_id": job.company_id, "company_name": job.company.name,
            "website_url": job.company.website_url, "status": job.status, "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts, "last_error_code": job.last_error_code,
            "last_error_message": job.last_error_message, "next_attempt_at": job.next_attempt_at,
            "created_at": job.created_at, "started_at": job.started_at, "finished_at": job.finished_at}


@router.post("/runs", status_code=201)
def start_run(body: RunIn, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
              db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    ids = company_ids_for_request(db, body.company_ids, body.upload_id, body.all_companies)
    run, created, skipped = create_run(db, ids, idempotency_key, created_by=user.id)
    return run_created_response(run, created, skipped)


@router.get("/runs")
def list_runs(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    return paginate(db, select(Run).order_by(Run.id.desc()), params, lambda r: run_json(r, job_counts(db, r.id)))


def _get_run(db, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise not_found("Run", run_id)
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    return run_json(_get_run(db, run_id), job_counts(db, run_id))


@router.get("/runs/{run_id}/items")
def run_items(run_id: int, status: JobStatus | None = None, params: PageParams = Depends(page_params),
              db: Session = Depends(get_db)):
    _get_run(db, run_id)
    stmt = select(Job).join(Company).where(Job.run_id == run_id).order_by(Job.id)
    if status:
        stmt = stmt.where(Job.status == status)
    return paginate(db, stmt, params, item_json)


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(require_reviewer)])
def cancel(run_id: int, db: Session = Depends(get_db)):
    run, cancelled_now = cancel_run(db, run_id)
    return {**run_json(run, job_counts(db, run_id)), "cancelled_now": cancelled_now}


@router.post("/runs/{run_id}/retry-failed", dependencies=[Depends(require_reviewer)])
def retry_failed_jobs(run_id: int, db: Session = Depends(get_db)):
    requeued = retry_failed(db, run_id)
    return {**run_json(_get_run(db, run_id), job_counts(db, run_id)), "requeued": requeued}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("Job", job_id)
    attempts = db.scalars(select(Attempt).where(Attempt.job_id == job_id).order_by(Attempt.attempt_no)).all()
    events = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id)).all()
    pages = db.scalars(select(Page).where(Page.job_id == job_id).order_by(Page.depth, Page.id)).all()
    return {
        **item_json(job), "run_id": job.run_id, "lease_owner": job.lease_owner,
        "lease_expires_at": job.lease_expires_at, "heartbeat_at": job.heartbeat_at,
        "classifications": db.scalar(select(func.count()).select_from(Classification)
                                     .where(Classification.job_id == job_id)),
        "attempts": [{"attempt_no": a.attempt_no, "worker_id": a.worker_id, "status": a.status,
                      "error_code": a.error_code, "error_message": a.error_message,
                      "started_at": a.started_at, "finished_at": a.finished_at} for a in attempts],
        "events": [{"from_status": e.from_status, "to_status": e.to_status, "reason": e.reason,
                    "worker_id": e.worker_id, "created_at": e.created_at} for e in events],
        "pages": [{"url": p.url, "final_url": p.final_url, "depth": p.depth, "outcome": p.outcome,
                   "http_status": p.http_status, "byte_size": p.byte_size, "title": p.title,
                   "fetched_at": p.fetched_at} for p in pages],
    }


@router.post("/jobs/{job_id}/retry", dependencies=[Depends(require_reviewer)])
def retry(job_id: int, db: Session = Depends(get_db)):
    job = retry_job(db, job_id)
    return item_json(job)
