"""Runs: idempotency, duplicates, already-in-progress, cancel, retry, run status rules."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db.models import Job, JobEvent, Run
from app.services.runs import refresh_run_status
from tests.factories import ensure_policy, make_company, make_run


@pytest.fixture(autouse=True)
def policy(db):
    """Runs need the policy version they are created under (normally made by the seed script)."""
    ensure_policy(db)


def test_policy_missing_is_a_clear_409(api, db):
    from app.db.models import PolicyVersion
    db.delete(db.get(PolicyVersion, "v1"))
    db.flush()
    r = api.post("/api/runs", json={"company_ids": [make_company(db).id]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "POLICY_MISSING"


def test_same_idempotency_key_returns_the_same_run(api, db):
    c = make_company(db)
    first = api.post("/api/runs", json={"company_ids": [c.id]}, headers={"Idempotency-Key": "abc-1"})
    again = api.post("/api/runs", json={"company_ids": [c.id]}, headers={"Idempotency-Key": "abc-1"})
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["run_id"] == again.json()["run_id"]
    assert again.json()["created"] is False
    assert db.scalar(select(func.count()).select_from(Run)) == 1
    assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_duplicate_ids_collapse_and_unknown_ids_are_skipped(api, db):
    a, b = make_company(db, 1), make_company(db, 2)
    body = api.post("/api/runs", json={"company_ids": [a.id, b.id, a.id, 999]}).json()
    assert body["total_items"] == 2
    assert body["skipped"] == [{"company_id": 999, "reason": "not_found"}]


def test_company_with_an_active_job_is_skipped(api, db):
    busy, free = make_company(db, 1), make_company(db, 2)
    make_run(db, [busy], statuses=["running"])
    body = api.post("/api/runs", json={"company_ids": [busy.id, free.id]}).json()
    assert body["total_items"] == 1
    assert body["skipped"] == [{"company_id": busy.id, "reason": "already_in_progress"}]

    r = api.post("/api/runs", json={"company_ids": [busy.id]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOTHING_TO_RUN"


def test_run_from_upload_and_all_companies(api, db):
    upload = api.post("/api/uploads", files={"file": ("c.csv", b"company_name,website\nA,a.example\nB,b.example\n")})
    by_upload = api.post("/api/runs", json={"upload_id": upload.json()["upload_id"]}).json()
    assert by_upload["total_items"] == 2
    r = api.post("/api/runs", json={"company_ids": [1], "all_companies": True})
    assert r.status_code == 422  # exactly one source allowed


def test_run_detail_progress_and_items(api, db):
    companies = [make_company(db, n) for n in range(1, 5)]
    run, _ = make_run(db, companies, statuses=["completed", "failed", "running", "queued"])
    body = api.get(f"/api/runs/{run.id}").json()
    assert body["counts"]["completed"] == 1 and body["counts"]["queued"] == 1
    assert body["progress"] == {"done": 2, "total": 4, "percent": 50.0}
    items = api.get(f"/api/runs/{run.id}/items?status=failed").json()
    assert items["total"] == 1 and items["items"][0]["company_name"] == "Co-op 2"


def test_cancel_cancels_queued_jobs_and_waits_for_running_ones(api, db):
    companies = [make_company(db, n) for n in range(1, 4)]
    run, jobs = make_run(db, companies, statuses=["queued", "running", "completed"])
    run.status = "running"
    db.flush()

    body = api.post(f"/api/runs/{run.id}/cancel").json()
    assert body["cancelled_now"] == 1
    assert body["status"] == "cancelling"  # one job is still running
    assert [j.status for j in jobs] == ["cancelled", "running", "completed"]  # finished job untouched

    jobs[1].status = "cancelled"  # what the worker does when it notices the cancel
    db.flush()
    refresh_run_status(db, run.id)
    assert run.status == "cancelled"
    assert api.post(f"/api/runs/{run.id}/cancel").status_code == 409  # already finished


def test_retry_requeues_a_failed_job_and_keeps_history(api, db):
    company = make_company(db)
    run, (job,) = make_run(db, [company], statuses=["failed"], attempt_count=3, max_attempts=3)
    job.last_error_code = "AI_UNAVAILABLE"
    run.status = "failed"
    db.flush()

    body = api.post(f"/api/jobs/{job.id}/retry").json()
    assert body["status"] == "queued" and body["last_error_code"] is None
    assert body["attempt_count"] == 3 and body["max_attempts"] == 6  # history kept, fresh budget
    assert db.get(Run, run.id).status == "running"
    assert db.scalar(select(JobEvent.reason).where(JobEvent.job_id == job.id)) == "manual retry"

    again = api.post(f"/api/jobs/{job.id}/retry")
    assert again.status_code == 409 and again.json()["error"]["code"] == "JOB_NOT_RETRYABLE"


def test_retry_failed_for_a_run(api, db):
    companies = [make_company(db, n) for n in range(1, 4)]
    run, jobs = make_run(db, companies, statuses=["failed", "cancelled", "completed"])
    body = api.post(f"/api/runs/{run.id}/retry-failed").json()
    assert body["requeued"] == 2
    assert [j.status for j in jobs] == ["queued", "queued", "completed"]


@pytest.mark.parametrize(
    "statuses,cancel,expected",
    [
        (["completed", "review_required"], False, "completed"),
        (["completed", "failed"], False, "completed_with_errors"),
        (["failed", "failed"], False, "failed"),
        (["completed", "cancelled"], True, "cancelled"),
        (["completed", "running"], False, "running"),
        (["running", "cancelled"], True, "cancelling"),
        (["queued", "queued"], False, "queued"),
    ],
)
def test_run_status_recompute(db, statuses, cancel, expected):
    run, _ = make_run(db, [make_company(db, n) for n in range(1, len(statuses) + 1)], statuses=statuses)
    if cancel:
        run.cancel_requested_at = datetime.now(UTC)
    db.flush()
    refresh_run_status(db, run.id)
    assert run.status == expected
    assert (run.finished_at is not None) == (expected in ("completed", "completed_with_errors", "failed", "cancelled"))
