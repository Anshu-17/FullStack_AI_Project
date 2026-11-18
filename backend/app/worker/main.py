"""Worker entry point:  python -m app.worker.main

One process, `worker_concurrency` threads (default 2). Each thread loops:
    recover expired leases -> claim the next ready job -> process it -> repeat
    (sleep 2 s when there is nothing to do)

Stopping: Ctrl+C / SIGTERM -> stop claiming, wait up to 30 s for jobs in progress, exit.
A hard kill is also safe: the killed job's lease expires and another loop recovers it.

Not distributed: several worker PROCESSES would also work (claims use SKIP LOCKED and
leases are in the database), but this project runs one process with threads.
"""
import os
import signal
import socket
import threading
import time

import structlog

from app.config import settings
from app.db.session import SessionLocal
from app.log_config import get_logger, setup_logging
from app.worker.leases import claim_next_job, recover_expired_leases
from app.worker.process import process_job

IDLE_SLEEP_SECONDS = 2
SHUTDOWN_GRACE_SECONDS = 30

log = get_logger("worker")
stopping = threading.Event()


def worker_loop(worker_id: str) -> None:
    structlog.contextvars.bind_contextvars(worker_id=worker_id)
    log.info("worker.thread_started")
    while not stopping.is_set():
        try:
            with SessionLocal() as db:
                recover_expired_leases(db)
                job_id = claim_next_job(db, worker_id)
            if job_id is None:
                stopping.wait(IDLE_SLEEP_SECONDS)  # nothing to do; wakes early on shutdown
                continue
            process_job(job_id, worker_id)
        except Exception:
            log.exception("worker.loop_error")  # e.g. database briefly down: wait and try again
            stopping.wait(IDLE_SLEEP_SECONDS)
    log.info("worker.thread_stopped")


def request_stop(*_):
    if not stopping.is_set():
        log.info("worker.stopping", grace_seconds=SHUTDOWN_GRACE_SECONDS)
        stopping.set()


def main() -> None:
    setup_logging()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    base_id = f"{socket.gethostname()}:{os.getpid()}"
    log.info("worker.started", worker=base_id, threads=settings.worker_concurrency,
             lease_seconds=settings.job_lease_seconds)

    threads = [threading.Thread(target=worker_loop, args=(f"{base_id}:t{n}",), daemon=True, name=f"worker-{n}")
               for n in range(1, settings.worker_concurrency + 1)]
    for t in threads:
        t.start()

    while not stopping.is_set():  # the main thread just waits for a signal
        time.sleep(0.5)

    deadline = time.monotonic() + SHUTDOWN_GRACE_SECONDS
    for t in threads:
        t.join(timeout=max(0.0, deadline - time.monotonic()))
    still_busy = [t.name for t in threads if t.is_alive()]
    if still_busy:
        log.warning("worker.exit_with_jobs_in_progress", threads=still_busy,
                    note="their leases will expire and the jobs will be recovered")
    log.info("worker.stopped")


if __name__ == "__main__":
    main()
