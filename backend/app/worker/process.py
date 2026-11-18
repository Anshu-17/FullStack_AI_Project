"""Process ONE claimed job: crawl -> classify -> finalize, with a heartbeat running alongside.

Fencing ("no duplicate finalized outcome"): every final write goes through _finalize(), which
first locks the job row (SELECT ... FOR UPDATE) and checks it is STILL running with
lease_owner == this worker. If our lease expired and another worker took the job over, we save
NOTHING and log LEASE_LOST. The unique (job_id, category) rule on classifications is the second
safety net.

Errors:
- permanent (bad / unsafe start URL)                  -> failed at once
- retryable (NO_CONTENT, AI_UNAVAILABLE, unexpected)   -> back to the queue with backoff
  (10 s, 20 s, 40 s ... max 300 s, +0-25 % jitter), or failed when no attempts are left
"""
import random
import threading
from datetime import timedelta

import structlog
from sqlalchemy import exists, func, select

from app.classifier.pipeline import AIUnavailableError, NoContentError, run_classification, save_classifications
from app.config import settings
from app.crawler.crawl import crawl_site
from app.crawler.store import save_pages
from app.db.enums import AttemptStatus, JobStatus, PageOutcome
from app.db.models import Attempt, Job, JobEvent, Page, Run
from app.db.session import SessionLocal
from app.log_config import get_logger
from app.services.runs import refresh_run_status
from app.worker.leases import heartbeat

log = get_logger("worker.process")

BACKOFF_BASE_SECONDS = 10
BACKOFF_MAX_SECONDS = 300


class PermanentJobError(Exception):
    """Retrying cannot help (e.g. the website address is invalid or points somewhere private)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CancelRequested(Exception):
    pass


def backoff_seconds(attempt: int) -> float:
    """min(300, 10 * 2^(attempt-1)) seconds, plus 0-25 % random jitter (so retries don't all fire together)."""
    base = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
    return base * (1 + random.uniform(0, 0.25))


# ------------------------------------------------------------------ heartbeat thread

def _heartbeat_loop(job_id: int, worker_id: str, stop: threading.Event) -> None:
    structlog.contextvars.bind_contextvars(worker_id=worker_id, job_id=job_id)
    interval = max(1.0, settings.job_lease_seconds / 3)  # renew well before the lease runs out
    while not stop.wait(interval):
        try:
            with SessionLocal() as db:
                if not heartbeat(db, job_id, worker_id):
                    log.warning("job.heartbeat_lost_lease", error_code="LEASE_LOST")
                    return  # someone else owns it now; finalize will refuse to save
        except Exception:
            log.exception("job.heartbeat_failed")  # e.g. DB blip: try again next interval


# ------------------------------------------------------------------ finalize (fenced)

def _finalize(job_id: int, worker_id: str, *, status: str, attempt_status: str, reason: str,
              error_code: str | None = None, error_message: str | None = None,
              classification=None, retry_in_seconds: float | None = None) -> bool:
    """Write the job's outcome in ONE transaction, only if we still hold the lease. Returns False if not."""
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job.status != JobStatus.RUNNING or job.lease_owner != worker_id:
            log.warning("job.lease_lost", error_code="LEASE_LOST", wanted_status=status,
                        current_status=str(job.status), current_owner=job.lease_owner)
            db.rollback()
            return False

        if classification is not None:
            save_classifications(db, job_id, classification)  # the 7 rows + evidence, same transaction

        attempt = db.scalar(select(Attempt).where(Attempt.job_id == job_id, Attempt.attempt_no == job.attempt_count))
        if attempt:
            attempt.status, attempt.finished_at = attempt_status, func.now()
            attempt.error_code, attempt.error_message = error_code, error_message

        db.add(JobEvent(job_id=job_id, from_status=JobStatus.RUNNING, to_status=status, reason=reason,
                        worker_id=worker_id))
        job.status = status
        job.lease_owner = job.lease_expires_at = None
        job.last_error_code, job.last_error_message = error_code, error_message
        if status == JobStatus.QUEUED:
            job.next_attempt_at = func.now() + timedelta(seconds=retry_in_seconds or 0)
        else:
            job.finished_at = func.now()
        db.flush()
        refresh_run_status(db, job.run_id)
        db.commit()
    log.info("job.finished", status=str(status), error_code=error_code, reason=reason)
    return True


def _fail_or_retry(job_id: int, worker_id: str, attempt: int, max_attempts: int, code: str, message: str) -> None:
    if attempt < max_attempts:
        delay = backoff_seconds(attempt)
        _finalize(job_id, worker_id, status=JobStatus.QUEUED, attempt_status=AttemptStatus.FAILED,
                  error_code=code, error_message=message, retry_in_seconds=delay,
                  reason=f"{code}: retry in {delay:.0f} s (attempt {attempt} of {max_attempts})")
    else:
        _finalize(job_id, worker_id, status=JobStatus.FAILED, attempt_status=AttemptStatus.FAILED,
                  error_code=code, error_message=message, reason=f"{code}: no attempts left")


# ------------------------------------------------------------------ the job

def _cancel_requested(job_id: int) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(Run.cancel_requested_at).join(Job, Job.run_id == Run.id)
                         .where(Job.id == job_id)) is not None


def _crawl_and_save(job_id: int, start_url: str) -> None:
    crawl = crawl_site(start_url)
    with SessionLocal() as db:
        save_pages(db, job_id, crawl)  # upsert: safe if a previous attempt saved some of them
        db.commit()
    if crawl.stopped_reason == "invalid_start_url":
        raise PermanentJobError("INVALID_URL", f"'{start_url}' is not a valid website address")
    first = crawl.pages[0] if crawl.pages else None
    if first is not None and first.outcome == PageOutcome.BLOCKED_UNSAFE:
        raise PermanentJobError("BLOCKED_UNSAFE", f"start URL blocked by the safety check: {first.error_detail}")


def process_job(job_id: int, worker_id: str) -> None:
    """Run one claimed job to a final state (completed / review_required / queued-for-retry / failed / cancelled)."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run_id, attempt, max_attempts = job.run_id, job.attempt_count, job.max_attempts
        start_url = job.company.website_url
        has_pages = db.scalar(select(exists().where(
            Page.job_id == job_id, Page.outcome == PageOutcome.OK, Page.text_content.is_not(None))))
    structlog.contextvars.bind_contextvars(worker_id=worker_id, job_id=job_id, run_id=run_id, attempt=attempt)

    stop = threading.Event()
    beat = threading.Thread(target=_heartbeat_loop, args=(job_id, worker_id, stop), daemon=True)
    beat.start()
    try:
        if _cancel_requested(job_id):
            raise CancelRequested()

        if has_pages:
            log.info("job.reusing_pages", reason="ok pages saved by an earlier attempt; not crawling again")
        else:
            _crawl_and_save(job_id, start_url)

        if _cancel_requested(job_id):  # checked again: crawling takes a while
            raise CancelRequested()

        with SessionLocal() as db:
            result = run_classification(db, job_id)  # AI calls (usage rows are committed as it goes)

        final = JobStatus.REVIEW_REQUIRED if result.needs_review else JobStatus.COMPLETED
        _finalize(job_id, worker_id, status=final, attempt_status=AttemptStatus.SUCCEEDED, classification=result,
                  reason=f"classified with {result.provider}; statuses {result.status_counts}")

    except CancelRequested:
        _finalize(job_id, worker_id, status=JobStatus.CANCELLED, attempt_status=AttemptStatus.FAILED,
                  error_code="CANCELLED", reason="run cancelled; stopped before saving results")
    except PermanentJobError as exc:
        _finalize(job_id, worker_id, status=JobStatus.FAILED, attempt_status=AttemptStatus.FAILED,
                  error_code=exc.code, error_message=str(exc), reason=f"{exc.code}: permanent, not retried")
    except (NoContentError, AIUnavailableError) as exc:
        _fail_or_retry(job_id, worker_id, attempt, max_attempts, exc.code, str(exc)[:500])
    except Exception as exc:
        log.exception("job.unexpected_error")
        _fail_or_retry(job_id, worker_id, attempt, max_attempts, "INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"[:500])
    finally:
        stop.set()
        beat.join(timeout=5)
        structlog.contextvars.unbind_contextvars("job_id", "run_id", "attempt")
