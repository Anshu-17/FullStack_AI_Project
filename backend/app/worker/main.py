"""Worker entry point:  python -m app.worker.main

Stage 0 version: a loop that logs a heartbeat and stops cleanly on Ctrl+C / SIGTERM.
Stage 5 will make it: claim queued jobs (with a lease), run the LangGraph pipeline,
save results in one transaction, and recover expired leases after a crash.
"""
import os
import signal
import socket
import time

import structlog

from app.log_config import get_logger, setup_logging

setup_logging()
log = get_logger("worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
running = True


def stop(*_):
    global running
    running = False
    log.info("worker.stopping")


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    structlog.contextvars.bind_contextvars(worker_id=WORKER_ID)
    log.info("worker.started")
    while running:
        log.info("worker.heartbeat")
        for _ in range(10):  # sleep in small steps so shutdown is quick
            if not running:
                break
            time.sleep(1)
    log.info("worker.stopped")


if __name__ == "__main__":
    main()
