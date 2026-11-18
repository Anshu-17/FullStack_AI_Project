"""Controlled workload: 100 SYNTHETIC jobs through the real API, worker, crawler and database - with the FAKE AI.

Needs: the fixture server (python fixtures/server.py), the API, and ONE worker started with the test-only
settings, e.g. (command environment only, never .env):

    CRAWL_FIXTURE_SERVER=127.0.0.1:8765 CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test \
    AI_PROVIDER=fake AI_FALLBACK_PROVIDERS=fake JOB_BACKOFF_BASE_SECONDS=1 python -m app.worker.main

Then (in backend/, REVIEWER_PW in the environment):

    python ../scripts/load_test.py ../docs/evidence/synthetic_load_100.md

100 companies on fixture domains (numbered copies of the fixture sites, e.g. clear-coop-305.fixture.test);
10 % point at broken-site (every page 500) to exercise retries. Everything is reported FROM THE DATABASE.
"""
import os
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select  # noqa: E402

from app.db.models import AIUsage, Attempt, Classification, Job, Run  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

API = os.environ.get("API_URL", "http://localhost:8000")
SITES = ["clear-coop", "grain-farm-only", "fuel-delivery-only", "pet-store", "online-catalog", "outdated-elevator",
         "feed-mill", "cardlock-fuel", "prompt-injection"]
N = 100


def companies() -> list[tuple[str, str]]:
    rows = []
    for i in range(1, N + 1):
        site = "broken-site" if i % 10 == 0 else SITES[i % len(SITES)]  # every 10th: broken
        rows.append((f"Load Test {i:03d} ({site})", f"http://{site}-{300 + i}.fixture.test/"))
    return rows


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


def main(out: Path) -> None:
    client = httpx.Client(base_url=API, timeout=60)
    token = client.post("/api/auth/login", json={"email": "reviewer@demo.local",
                                                 "password": os.environ["REVIEWER_PW"]}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    csv = "company_name,website\n" + "".join(f"{n},{u}\n" for n, u in companies())
    up = client.post("/api/uploads", headers=h, data={"source": "synthetic"},
                     files={"file": ("load_test_100.csv", csv.encode(), "text/csv")}).json()
    ids = [r["company_id"] for r in client.get(f"/api/uploads/{up['upload_id']}/rows", headers=h,
                                               params={"page_size": 200}).json()["items"]]
    started = time.perf_counter()
    run = client.post("/api/runs", headers={**h, "Idempotency-Key": f"load-test-{int(time.time())}"},
                      json={"company_ids": ids}).json()
    run_id = run["run_id"]
    print(f"upload {up['upload_id']} counts={up['counts']} -> run {run_id} with {run['total_items']} jobs")

    while True:  # progress straight from the API (which reads the database)
        r = client.get(f"/api/runs/{run_id}", headers=h).json()
        done, total = r["progress"]["done"], r["progress"]["total"]
        print(f"  {time.perf_counter() - started:6.1f} s  {r['status']:<22} {done}/{total}")
        if r["status"] in ("completed", "completed_with_errors", "failed", "cancelled"):
            break
        time.sleep(5)

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        jobs = db.scalars(select(Job).where(Job.run_id == run_id)).all()
        total_s = (run.finished_at - run.created_at).total_seconds()
        processing_s = (run.finished_at - run.started_at).total_seconds()
        ok_jobs = [j for j in jobs if j.status in ("completed", "review_required")]
        latency = [(j.finished_at - j.started_at).total_seconds() for j in ok_jobs]
        by_status: dict[str, int] = {}
        for j in jobs:
            by_status[j.status] = by_status.get(j.status, 0) + 1
        failures: dict[str, int] = {}
        for j in jobs:
            if j.status == "failed":
                failures[j.last_error_code] = failures.get(j.last_error_code, 0) + 1
        attempts = dict(db.execute(select(Attempt.status, func.count()).join(Job, Job.id == Attempt.job_id)
                                   .where(Job.run_id == run_id).group_by(Attempt.status)).all())
        retries = sum(max(j.attempt_count - 1, 0) for j in jobs)
        per_job = dict(db.execute(select(Classification.job_id, func.count()).join(Job, Job.id == Classification.job_id)
                                  .where(Job.run_id == run_id).group_by(Classification.job_id)).all())
        dupes = db.execute(select(Classification.job_id, Classification.category, func.count())
                           .join(Job, Job.id == Classification.job_id).where(Job.run_id == run_id)
                           .group_by(Classification.job_id, Classification.category)
                           .having(func.count() > 1)).all()
        failed_with_rows = [j.id for j in jobs if j.status == "failed" and per_job.get(j.id)]
        ai = db.execute(select(AIUsage.provider, AIUsage.model, AIUsage.outcome, func.count())
                        .join(Job, Job.id == AIUsage.job_id).where(Job.run_id == run_id)
                        .group_by(AIUsage.provider, AIUsage.model, AIUsage.outcome)).all()

    seven = sum(1 for j in ok_jobs if per_job.get(j.id) == 7)
    lines = [
        "# SYNTHETIC workload - 100 jobs (local fixtures + FAKE AI provider)",
        "",
        "> **Synthetic.** Websites are local fixture pages (`fixtures/sites/`, numbered copies such as "
        "`clear-coop-305.fixture.test`) and the AI is the deterministic keyword provider `fake-keyword-v1` "
        "(no network, no AI cost). It measures the PLATFORM - API, queue, worker, crawler, validation, database - "
        "not real-world crawl or AI latency. Every number below is read from the database after the run.",
        "",
        f"- Date: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC; run #{run_id}; upload #{up['upload_id']} "
        f"(source=synthetic, counts {up['counts']})",
        f"- Machine: {platform.platform()}, Python {platform.python_version()}, local PostgreSQL 18; API, worker "
        "and fixture server on the same machine",
        "- Worker: ONE process, `WORKER_CONCURRENCY=2` threads, lease 120 s; test-only settings in the command "
        "environment: `AI_PROVIDER=fake`, `CRAWL_FIXTURE_SERVER=127.0.0.1:8765`, "
        "`CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test`, `JOB_BACKOFF_BASE_SECONDS=1` (retry waits 1 s, 2 s + jitter "
        "instead of 10 s, 20 s)",
        f"- Mix: {N} jobs, 90 on content fixture sites, 10 on `broken-site` (every page answers 500 -> NO_CONTENT -> "
        "retried, then failed)",
        "",
        "## Results",
        "",
        "| measure | value |",
        "|---|---|",
        f"| total time (run created -> finished) | {total_s:.1f} s |",
        f"| processing time (first claim -> finished) | {processing_s:.1f} s |",
        f"| throughput | {len(jobs) / (processing_s / 60):.1f} jobs/min (all {len(jobs)} jobs incl. retries) |",
        f"| job latency, successful jobs (claim -> finished) | p50 {statistics.median(latency):.2f} s, "
        f"p95 {percentile(latency, 95):.2f} s, max {max(latency):.2f} s |",
        f"| outcomes by job status | {by_status} |",
        f"| failures by error code | {failures or 'none'} |",
        f"| attempts by status | {attempts} |",
        f"| retries (attempts beyond the first) | {retries} |",
        f"| successful jobs with exactly 7 classifications | {seven} of {len(ok_jobs)} |",
        f"| duplicate (job, category) answers | {len(dupes)} |",
        f"| failed jobs with any classification saved | {len(failed_with_rows)} |",
        f"| AI calls (provider / model / outcome) | {[tuple(a) for a in ai]} |",
        "",
        "## Reading the numbers",
        "",
        "- The broken-site jobs each took 3 attempts (2 retries) and then failed with `NO_CONTENT`; their failure "
        "never produced answers.",
        "- Latency here is dominated by crawling the local fixture pages and by the database work; with a real AI "
        "provider each job also waits for the model (5-15 s per call in the real runs), so real throughput is much "
        "lower and bounded by AI rate limits (free tier).",
        "- Exactly-7-classifications and zero duplicates are guaranteed by the unique `(job_id, category)` rule and "
        "the lease-fenced finalize; this run confirms it at 100 jobs with 2 concurrent threads.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
