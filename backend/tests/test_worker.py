"""The worker: claiming, lease recovery, and processing a job end to end.

These tests use `fresh_db` (real commits) because the worker uses its own sessions and threads.
Crawling and AI are faked: no network, no real model.
"""
import threading
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select, update

from app.classifier import pipeline
from app.classifier.schema import ClassificationOutput
from app.crawler.crawl import CrawledPage, CrawlResult
from app.db.models import Attempt, Classification, Job, JobEvent, Page, Run
from app.worker import process
from app.worker.leases import claim_next_job, recover_expired_leases
from tests.factories import make_company, make_run

HOME_TEXT = ("Prairie Co-op buys grain at its elevators and posts daily cash bids. "
             "We deliver propane and diesel. Our agronomy team sells seed and fertilizer.")


# ------------------------------------------------------------------ fakes

def fake_crawl(url):
    return CrawlResult(start_url=url, pages=[CrawledPage(url=url, final_url=url, http_status=200, outcome="ok",
                                                         content_type="text/html", byte_size=500, text=HOME_TEXT)])


def good_output():
    def yes(category, quote):
        return {"category": category, "status": "yes", "explanation": "on the site",
                "evidence": [{"passage_id": "P1", "quote": quote}]}

    def nf(category):
        return {"category": category, "status": "not_found", "explanation": "not mentioned", "evidence": []}

    return ClassificationOutput.model_validate({"decisions": [
        yes("agronomy", "sells seed and fertilizer"), yes("grain", "buys grain at its elevators"),
        yes("energy", "We deliver propane and diesel"), nf("feed"), nf("gas_station"), nf("retail_store")]})


class FakeModel:
    def __init__(self, answer=None, error=None, on_call=None):
        self.answer, self.error, self.on_call, self.calls = answer, error, on_call, 0

    def invoke(self, _messages):
        self.calls += 1
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        return {"raw": AIMessage(content="{}", usage_metadata={"input_tokens": 10, "output_tokens": 5,
                                                                "total_tokens": 15}),
                "parsed": self.answer, "parsing_error": None}


class HTTP503(Exception):
    status_code = 503


class LogRecorder:
    """Stands in for the module's structlog logger so tests can see what was logged."""

    def __init__(self):
        self.events = []

    def _record(self, event, **kw):
        self.events.append((event, kw))

    info = warning = exception = error = _record


@pytest.fixture()
def worker_env(fresh_db, crawler_settings, monkeypatch):
    """Two fake AI providers, fake crawler, no real sleeping. Returns helpers."""
    crawler_settings(ai_provider="google", ai_fallback_providers="groq", google_api_key="k", google_model="g",
                     groq_api_key="k", groq_model="q", ai_price_input_per_mtok=None, ai_price_output_per_mtok=None)
    monkeypatch.setattr(pipeline, "sleep", lambda s: None)
    monkeypatch.setattr(process, "crawl_site", fake_crawl)
    recorder = LogRecorder()
    monkeypatch.setattr(process, "log", recorder)
    models = {"google": FakeModel(good_output()), "groq": FakeModel(good_output())}
    monkeypatch.setattr(pipeline, "build_structured_model", lambda provider: models[provider])

    def new_job(n=1, **job_fields):
        with fresh_db() as s:
            run, (job,) = make_run(s, [make_company(s, n)], **job_fields)
            s.commit()
            return job.id, run.id

    return {"Session": fresh_db, "models": models, "log": recorder, "new_job": new_job}


def state(Session, job_id):
    with Session() as s:
        job = s.get(Job, job_id)
        return {
            "status": job.status, "attempts": [(a.attempt_no, a.status, a.error_code) for a in
                                               s.scalars(select(Attempt).where(Attempt.job_id == job_id)
                                                         .order_by(Attempt.attempt_no))],
            "classifications": s.scalar(select(func.count()).select_from(Classification)
                                        .where(Classification.job_id == job_id)),
            "error": job.last_error_code, "lease_owner": job.lease_owner, "next_attempt_at": job.next_attempt_at,
            "run_status": s.get(Run, job.run_id).status, "attempt_count": job.attempt_count,
        }


def claim(Session, worker="w1"):
    with Session() as s:
        return claim_next_job(s, worker)


# ------------------------------------------------------------------ claiming

def test_two_concurrent_workers_never_claim_the_same_job(fresh_db):
    with fresh_db() as s:
        make_run(s, [make_company(s, n) for n in range(1, 21)])
        s.commit()
    claimed: dict[str, list[int]] = {"a": [], "b": []}
    start = threading.Barrier(2)

    def worker(name):
        start.wait()
        while (job_id := claim(fresh_db, name)) is not None:
            claimed[name].append(job_id)

    threads = [threading.Thread(target=worker, args=(n,)) for n in claimed]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert not set(claimed["a"]) & set(claimed["b"])  # no job claimed twice
    assert len(claimed["a"]) + len(claimed["b"]) == 20
    with fresh_db() as s:
        assert s.scalar(select(func.count()).select_from(Attempt)) == 20


def test_claim_sets_lease_attempt_and_starts_the_run(worker_env):
    job_id, run_id = worker_env["new_job"]()
    assert claim(worker_env["Session"], "w1") == job_id
    with worker_env["Session"]() as s:
        job = s.get(Job, job_id)
        assert (job.status, job.lease_owner, job.attempt_count) == ("running", "w1", 1)
        assert job.lease_expires_at > datetime.now(UTC)
        assert s.get(Run, run_id).status == "running"


def test_jobs_of_a_cancelling_run_and_jobs_in_backoff_are_not_claimed(worker_env):
    Session = worker_env["Session"]
    cancelled_job, cancelled_run = worker_env["new_job"](1)
    later_job, _ = worker_env["new_job"](2)
    with Session() as s:
        s.get(Run, cancelled_run).cancel_requested_at = datetime.now(UTC)
        s.get(Job, later_job).next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
        s.commit()
    assert claim(Session) is None


# ------------------------------------------------------------------ recovery

def expire_lease(Session, job_id):
    with Session() as s:
        s.execute(update(Job).where(Job.id == job_id).values(lease_expires_at=func.now() - timedelta(seconds=1)))
        s.commit()


def test_expired_lease_abandons_attempt_and_requeues(worker_env):
    Session = worker_env["Session"]
    job_id, _ = worker_env["new_job"]()
    claim(Session, "crashed-worker")
    expire_lease(Session, job_id)

    with Session() as s:
        assert recover_expired_leases(s) == 1
    st = state(Session, job_id)
    assert st["status"] == "queued" and st["lease_owner"] is None
    assert st["attempts"] == [(1, "abandoned", "WORKER_LOST")]
    assert claim(Session, "w2") == job_id  # claimable again straight away


def test_expired_lease_with_no_attempts_left_fails_worker_lost(worker_env):
    Session = worker_env["Session"]
    job_id, _ = worker_env["new_job"](max_attempts=1)
    claim(Session, "crashed-worker")
    expire_lease(Session, job_id)
    with Session() as s:
        recover_expired_leases(s)
    st = state(Session, job_id)
    assert (st["status"], st["error"], st["run_status"]) == ("failed", "WORKER_LOST", "failed")


def test_live_lease_is_not_recovered(worker_env):
    job_id, _ = worker_env["new_job"]()
    claim(worker_env["Session"])
    with worker_env["Session"]() as s:
        assert recover_expired_leases(s) == 0
    assert state(worker_env["Session"], job_id)["status"] == "running"


# ------------------------------------------------------------------ process_job

def test_success_completes_with_seven_classifications(worker_env):
    Session = worker_env["Session"]
    job_id, _ = worker_env["new_job"]()
    process.process_job(claim(Session), "w1")
    st = state(Session, job_id)
    assert st["status"] == "completed"
    assert st["classifications"] == 7
    assert st["attempts"] == [(1, "succeeded", None)]
    assert st["run_status"] == "completed" and st["lease_owner"] is None


def test_ai_unavailable_backs_off_then_fails_and_never_saves_classifications(worker_env):
    Session, models = worker_env["Session"], worker_env["models"]
    models["google"].error = models["groq"].error = HTTP503()
    job_id, _ = worker_env["new_job"](max_attempts=2)

    process.process_job(claim(Session), "w1")
    st = state(Session, job_id)
    assert st["status"] == "queued" and st["error"] == "AI_UNAVAILABLE"
    assert st["next_attempt_at"] > datetime.now(UTC) + timedelta(seconds=9)  # backoff >= 10 s
    assert claim(Session) is None  # not claimable during backoff

    with Session() as s:  # pretend the backoff time has passed
        s.get(Job, job_id).next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        s.commit()
    process.process_job(claim(Session), "w1")
    st = state(Session, job_id)
    assert (st["status"], st["error"], st["run_status"]) == ("failed", "AI_UNAVAILABLE", "failed")
    assert st["attempts"] == [(1, "failed", "AI_UNAVAILABLE"), (2, "failed", "AI_UNAVAILABLE")]
    assert st["classifications"] == 0


def test_cancel_between_crawl_and_classify(worker_env, monkeypatch):
    Session, models = worker_env["Session"], worker_env["models"]
    job_id, run_id = worker_env["new_job"]()

    def crawl_then_cancel(url):
        with Session() as s:  # the user presses "cancel" while the crawl is running
            s.get(Run, run_id).cancel_requested_at = datetime.now(UTC)
            s.commit()
        return fake_crawl(url)

    monkeypatch.setattr(process, "crawl_site", crawl_then_cancel)
    process.process_job(claim(Session), "w1")
    st = state(Session, job_id)
    assert (st["status"], st["classifications"], st["run_status"]) == ("cancelled", 0, "cancelled")
    assert models["google"].calls == 0  # no AI call after the cancel


def test_lost_lease_before_finalize_saves_nothing(worker_env):
    Session, models = worker_env["Session"], worker_env["models"]
    job_id, _ = worker_env["new_job"]()

    def steal_lease():  # while the AI is "thinking", recovery hands the job to another worker
        with Session() as s:
            s.execute(update(Job).where(Job.id == job_id).values(lease_owner="other-worker"))
            s.commit()

    models["google"].on_call = steal_lease
    process.process_job(claim(Session), "w1")

    st = state(Session, job_id)
    assert st["classifications"] == 0                      # nothing written by the old owner
    assert st["status"] == "running" and st["lease_owner"] == "other-worker"
    assert any(kw.get("error_code") == "LEASE_LOST" for _, kw in worker_env["log"].events)


def test_retry_reuses_pages_saved_by_an_earlier_attempt(worker_env, monkeypatch):
    Session = worker_env["Session"]
    job_id, _ = worker_env["new_job"]()
    with Session() as s:
        s.add(Page(job_id=job_id, url="https://coop1.example/", depth=0, outcome="ok", text_content=HOME_TEXT))
        s.commit()

    def must_not_crawl(url):
        raise AssertionError("should reuse the saved pages")

    monkeypatch.setattr(process, "crawl_site", must_not_crawl)
    process.process_job(claim(Session), "w1")
    assert state(Session, job_id)["status"] == "completed"
    assert ("job.reusing_pages", {"reason": "ok pages saved by an earlier attempt; not crawling again"}) \
        in worker_env["log"].events


def test_unsafe_start_url_fails_permanently(worker_env, monkeypatch):
    Session = worker_env["Session"]
    job_id, _ = worker_env["new_job"]()
    monkeypatch.setattr(process, "crawl_site", lambda url: CrawlResult(start_url=url, pages=[
        CrawledPage(url=url, outcome="blocked_unsafe", error_detail="resolves to 10.0.0.5")]))
    process.process_job(claim(Session), "w1")
    st = state(Session, job_id)
    assert (st["status"], st["error"], st["attempt_count"]) == ("failed", "BLOCKED_UNSAFE", 1)  # not retried


def test_requeued_failed_job_runs_again(worker_env):
    Session, models = worker_env["Session"], worker_env["models"]
    models["google"].error = models["groq"].error = HTTP503()
    job_id, _ = worker_env["new_job"](max_attempts=1)
    process.process_job(claim(Session), "w1")
    assert state(Session, job_id)["status"] == "failed"

    from app.services.runs import retry_job
    with Session() as s:
        retry_job(s, job_id)
    models["google"].error = models["groq"].error = None
    process.process_job(claim(Session), "w1")
    st = state(Session, job_id)
    assert (st["status"], st["classifications"], st["attempt_count"]) == ("completed", 7, 2)
    with Session() as s:
        reasons = s.scalars(select(JobEvent.reason).where(JobEvent.job_id == job_id).order_by(JobEvent.id)).all()
    assert "manual retry" in reasons
