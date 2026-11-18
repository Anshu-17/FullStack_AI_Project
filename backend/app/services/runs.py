"""Runs and jobs: create, cancel, retry, and keep the run's status in line with its jobs.

Rules:
- Idempotency: a run created with an Idempotency-Key is returned again for the same key
  (the key is UNIQUE in the database, so even two simultaneous requests make one run).
- Duplicate company ids in one request collapse to one job.
- A company that already has a queued/running job (in any run) is skipped and reported as
  "already_in_progress" (also enforced by a partial unique index on jobs).
- Cancel: queued jobs are cancelled at once; running jobs finish their current step and the
  worker then cancels them. The run is "cancelling" until no job is running, then "cancelled".
- Retry: failed or cancelled jobs go back to the queue with a fresh attempt budget; the
  attempt history is kept.

Lock order (prevents deadlocks): the worker locks a JOB then its RUN; cancel / retry-failed
lock the RUN, then only rows the worker is not holding (queued / failed jobs).
"""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError, not_found
from app.classifier.taxonomy import POLICY_VERSION
from app.config import settings
from app.db.enums import JobStatus, RunStatus
from app.db.models import Company, Job, JobEvent, PolicyVersion, Run, UploadRow

ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)
SUCCEEDED = (JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED)
RUN_FINISHED = (RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_ERRORS, RunStatus.FAILED, RunStatus.CANCELLED)


def now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ status

def job_counts(db, run_id: int) -> dict[str, int]:
    """Jobs per status for one run (every status present, 0 if none) - straight from the database."""
    counts = dict(db.execute(select(Job.status, func.count()).where(Job.run_id == run_id).group_by(Job.status)).all())
    return {str(s): counts.get(str(s), 0) for s in JobStatus}


def refresh_run_status(db, run_id: int) -> Run:
    """Recompute the run's status from its jobs. Locks the run row so two workers finishing
    jobs of the same run at the same moment cannot both compute from stale counts.
    Does not commit (the caller's transaction does)."""
    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
    counts = job_counts(db, run_id)
    active = counts[JobStatus.QUEUED] + counts[JobStatus.RUNNING]
    succeeded = counts[JobStatus.COMPLETED] + counts[JobStatus.REVIEW_REQUIRED]
    unsuccessful = counts[JobStatus.FAILED] + counts[JobStatus.CANCELLED]

    if active:
        if run.cancel_requested_at:
            run.status = RunStatus.CANCELLING
        elif counts[JobStatus.RUNNING] or run.status != RunStatus.QUEUED:
            run.status = RunStatus.RUNNING
        run.finished_at = None
        return run

    if run.cancel_requested_at:
        run.status = RunStatus.CANCELLED
    elif unsuccessful == 0:
        run.status = RunStatus.COMPLETED              # every job completed or needs review
    elif succeeded == 0:
        run.status = RunStatus.FAILED                 # nothing succeeded
    else:
        run.status = RunStatus.COMPLETED_WITH_ERRORS  # partial success
    run.finished_at = run.finished_at or now()
    return run


# ------------------------------------------------------------------ create

def company_ids_for_request(db, company_ids=None, upload_id=None, all_companies=False) -> list[int]:
    if company_ids is not None:
        return list(company_ids)
    if upload_id is not None:
        if not db.scalar(select(func.count()).select_from(UploadRow).where(UploadRow.upload_id == upload_id)):
            raise not_found("Upload", upload_id)
        return list(db.scalars(select(UploadRow.company_id).where(
            UploadRow.upload_id == upload_id, UploadRow.company_id.is_not(None)).order_by(UploadRow.row_no)))
    if all_companies:
        return list(db.scalars(select(Company.id).order_by(Company.id)))
    raise ApiError(422, "VALIDATION_ERROR", "Give company_ids, upload_id or all_companies.")


def _run_by_key(db, key: str | None) -> Run | None:
    return db.scalar(select(Run).where(Run.idempotency_key == key)) if key else None


def create_run(db, company_ids: list[int], idempotency_key: str | None = None,
               source: str = "api") -> tuple[Run, bool, list[dict]]:
    """Returns (run, created, skipped). created=False means the Idempotency-Key was seen before."""
    existing = _run_by_key(db, idempotency_key)
    if existing:
        return existing, False, existing.config.get("skipped", [])
    if db.get(PolicyVersion, POLICY_VERSION) is None:
        raise ApiError(409, "POLICY_MISSING", f"Policy {POLICY_VERSION} is missing; run: python -m app.db.seed")

    wanted = list(dict.fromkeys(company_ids))  # duplicates collapse, order kept
    known = set(db.scalars(select(Company.id).where(Company.id.in_(wanted)))) if wanted else set()
    busy = set(db.scalars(select(Job.company_id).where(Job.company_id.in_(known), Job.status.in_(ACTIVE))))
    skipped = ([{"company_id": i, "reason": "not_found"} for i in wanted if i not in known]
               + [{"company_id": i, "reason": "already_in_progress"} for i in wanted if i in busy])
    todo = [i for i in wanted if i in known and i not in busy]
    if not todo:
        raise ApiError(409, "NOTHING_TO_RUN", "None of the requested companies can be started.", {"skipped": skipped})

    run = Run(policy_version=POLICY_VERSION, idempotency_key=idempotency_key, total_items=len(todo),
              config={"source": source, "requested": len(wanted), "skipped": skipped})
    db.add(run)
    db.flush()
    jobs = [Job(run_id=run.id, company_id=i, max_attempts=settings.job_max_attempts) for i in todo]
    db.add_all(jobs)
    db.flush()
    db.add_all([JobEvent(job_id=j.id, to_status=JobStatus.QUEUED, reason=f"created in run {run.id}") for j in jobs])
    try:
        db.commit()
    except IntegrityError as exc:
        # Lost a race: the same Idempotency-Key, or the same company started by another request.
        db.rollback()
        existing = _run_by_key(db, idempotency_key)
        if existing:
            return existing, False, existing.config.get("skipped", [])
        raise ApiError(409, "ALREADY_IN_PROGRESS",
                       "Some of these companies were just started by another request. Try again.") from exc
    return run, True, skipped


# ------------------------------------------------------------------ cancel / retry

def cancel_run(db, run_id: int) -> tuple[Run, int]:
    """Cancel queued jobs now; running jobs are cancelled by the worker at its next check."""
    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if run is None:
        raise not_found("Run", run_id)
    if run.status in RUN_FINISHED:
        raise ApiError(409, "RUN_FINISHED", f"Run {run_id} is already {run.status}.")
    run.cancel_requested_at = run.cancel_requested_at or now()
    # skip_locked: a job a worker is claiming at this instant is left alone; the worker sees the
    # cancel request when it starts and cancels the job itself.
    queued = db.scalars(select(Job).where(Job.run_id == run_id, Job.status == JobStatus.QUEUED)
                        .with_for_update(skip_locked=True)).all()
    for job in queued:
        job.status, job.finished_at = JobStatus.CANCELLED, now()
        db.add(JobEvent(job_id=job.id, from_status=JobStatus.QUEUED, to_status=JobStatus.CANCELLED,
                        reason="run cancelled before the job started"))
    db.flush()
    refresh_run_status(db, run_id)
    db.commit()
    return run, len(queued)


def _requeue(db, job: Job, reason: str) -> None:
    db.add(JobEvent(job_id=job.id, from_status=job.status, to_status=JobStatus.QUEUED, reason=reason))
    job.status = JobStatus.QUEUED
    job.lease_owner = job.lease_expires_at = job.heartbeat_at = None
    job.last_error_code = job.last_error_message = job.finished_at = None
    job.next_attempt_at = func.now()
    job.max_attempts = job.attempt_count + settings.job_max_attempts  # fresh budget; history kept


def _reopen_run(db, run_id: int) -> None:
    run = db.get(Run, run_id)
    run.cancel_requested_at = None  # a retried job must be claimable again
    db.flush()
    refresh_run_status(db, run_id)


def _commit_requeue(db) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "ALREADY_IN_PROGRESS",
                       "This company already has a queued or running job in another run.") from exc


def retry_job(db, job_id: int) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise not_found("Job", job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise ApiError(409, "JOB_NOT_RETRYABLE", f"Job {job_id} is {job.status}; only failed or cancelled jobs "
                       "can be retried.")
    _requeue(db, job, "manual retry")
    db.flush()
    _reopen_run(db, job.run_id)
    _commit_requeue(db)
    return job


def retry_failed(db, run_id: int) -> int:
    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if run is None:
        raise not_found("Run", run_id)
    jobs = db.scalars(select(Job).where(Job.run_id == run_id, Job.status.in_(
        [JobStatus.FAILED, JobStatus.CANCELLED])).with_for_update()).all()
    for job in jobs:
        _requeue(db, job, "retry failed jobs of the run")
    db.flush()
    if jobs:
        _reopen_run(db, run_id)
    _commit_requeue(db)
    return len(jobs)
