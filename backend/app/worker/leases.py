"""Job leases: how a worker takes a job, keeps it, and how abandoned jobs come back.

A lease = "worker X owns this job until time T". The worker renews it (heartbeat) while
working. If the worker crashes, nobody renews it; once T has passed, recover_expired_leases()
puts the job back in the queue (or fails it when no attempts are left).

All times use the DATABASE clock (now()), so several machines never disagree about expiry.
"""
from datetime import timedelta

from sqlalchemy import func, select, update

from app.config import settings
from app.db.enums import AttemptStatus, JobStatus, RunStatus
from app.db.models import Attempt, Job, JobEvent, Run
from app.log_config import get_logger
from app.services.runs import refresh_run_status

log = get_logger("worker.leases")


def lease_interval():
    return timedelta(seconds=settings.job_lease_seconds)


def claim_next_job(db, worker_id: str) -> int | None:
    """Take the next ready job, or None. Returns the job id.

    FOR UPDATE SKIP LOCKED: if another worker is claiming a row right now, we skip it instead of
    waiting - so two workers can never claim the same job, and neither blocks the other.
    """
    job = db.scalar(
        select(Job).join(Run, Run.id == Job.run_id)
        .where(Job.status == JobStatus.QUEUED,
               Job.next_attempt_at <= func.now(),              # backoff: not before its retry time
               Run.cancel_requested_at.is_(None),              # cancelled runs start nothing new
               Run.status.notin_([RunStatus.CANCELLING, RunStatus.CANCELLED]))
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=Job)  # lock only the job row
    )
    if job is None:
        db.rollback()
        return None

    job.status = JobStatus.RUNNING
    job.lease_owner = worker_id
    job.lease_expires_at = func.now() + lease_interval()
    job.heartbeat_at = func.now()
    job.attempt_count += 1
    job.started_at = job.started_at or func.now()
    db.add(Attempt(job_id=job.id, attempt_no=job.attempt_count, worker_id=worker_id, status=AttemptStatus.RUNNING))
    db.add(JobEvent(job_id=job.id, from_status=JobStatus.QUEUED, to_status=JobStatus.RUNNING,
                    reason=f"claimed (attempt {job.attempt_count})", worker_id=worker_id))
    job_id, run_id = job.id, job.run_id
    db.commit()

    # Separate short transaction: mark the run as started. Kept apart from the job lock above
    # so claim never holds a job lock while waiting for the run row (avoids deadlocks with cancel).
    db.execute(update(Run).where(Run.id == run_id, Run.status == RunStatus.QUEUED)
               .values(status=RunStatus.RUNNING, started_at=func.now()))
    db.commit()
    log.info("job.claimed", job_id=job_id, run_id=run_id, worker_id=worker_id)
    return job_id


def heartbeat(db, job_id: int, worker_id: str) -> bool:
    """Extend the lease - ONLY if this worker still owns the job. False = the lease was lost."""
    renewed = db.execute(
        update(Job).where(Job.id == job_id, Job.lease_owner == worker_id, Job.status == JobStatus.RUNNING)
        .values(lease_expires_at=func.now() + lease_interval(), heartbeat_at=func.now())
    ).rowcount
    db.commit()
    return renewed == 1


def recover_expired_leases(db) -> int:
    """Running jobs whose lease has expired (their worker died): abandon the attempt and
    re-queue the job, or fail it with WORKER_LOST when no attempts are left. Returns how many."""
    expired = db.scalars(
        select(Job).where(Job.status == JobStatus.RUNNING, Job.lease_expires_at < func.now())
        .order_by(Job.id).with_for_update(skip_locked=True)  # another worker recovering the same job? skip it
    ).all()
    for job in expired:
        attempt = db.scalar(select(Attempt).where(Attempt.job_id == job.id, Attempt.status == AttemptStatus.RUNNING)
                            .order_by(Attempt.attempt_no.desc()))
        if attempt:
            attempt.status, attempt.finished_at = AttemptStatus.ABANDONED, func.now()
            attempt.error_code = "WORKER_LOST"
            attempt.error_message = f"lease held by {job.lease_owner} expired without a heartbeat"

        lost_owner = job.lease_owner
        job.lease_owner = job.lease_expires_at = None
        if job.attempt_count < job.max_attempts:
            job.status, job.next_attempt_at = JobStatus.QUEUED, func.now()
            reason = f"lease of {lost_owner} expired; re-queued (attempt {job.attempt_count} abandoned)"
        else:
            job.status, job.finished_at = JobStatus.FAILED, func.now()
            job.last_error_code = "WORKER_LOST"
            job.last_error_message = f"worker {lost_owner} stopped responding and no attempts are left"
            reason = "lease expired; no attempts left -> failed"
        db.add(JobEvent(job_id=job.id, from_status=JobStatus.RUNNING, to_status=job.status, reason=reason))
        log.warning("job.lease_recovered", job_id=job.id, run_id=job.run_id, lost_owner=lost_owner,
                    new_status=str(job.status), attempt=job.attempt_count)
    db.flush()
    for run_id in {job.run_id for job in expired}:
        refresh_run_status(db, run_id)
    db.commit()
    return len(expired)
