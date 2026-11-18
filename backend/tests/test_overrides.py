"""Reviewer corrections: optimistic locking (scenario G), removal, history, human wins over a new scan (scenario E)."""
import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.api.errors import ApiError
from app.db.models import Classification, Override, User
from app.services.answers import final_answers
from app.services.overrides import create_override
from tests.factories import make_company, make_run


def correct(api, company_id, category="grain", new_status="not_found", expected=0, reason="checked with the co-op"):
    return api.post(f"/api/companies/{company_id}/overrides",
                    json={"category": category, "new_status": new_status, "reason": reason,
                          "expected_version": expected})


def scan(db, company, statuses: dict[str, str]):
    """A finished automated scan with the given answers."""
    _, (job,) = make_run(db, [company], statuses=["completed"])
    job.finished_at = datetime.now(UTC)
    for category, status in statuses.items():
        db.add(Classification(job_id=job.id, company_id=company.id, category=category, status=status,
                              provenance="rule" if category == "accounting" else "site",
                              explanation="automated", policy_version="v1"))
    db.flush()
    return job


def test_first_correction_then_a_follow_up(api, db):
    company = make_company(db)
    scan(db, company, {"grain": "yes"})

    first = correct(api, company.id, new_status="not_found", expected=0)
    assert first.status_code == 201, first.text
    assert first.json()["override"] == {"id": first.json()["override"]["id"], "version": 1,
                                        "old_status": "yes", "new_status": "not_found"}
    assert first.json()["answer"]["provenance"] == "human"

    detail = api.get(f"/api/companies/{company.id}").json()
    grain = next(a for a in detail["answers"] if a["category"] == "grain")
    assert grain["version"] == 1  # what the UI must send next time

    follow_up = correct(api, company.id, new_status="possible", expected=1)
    assert follow_up.status_code == 201 and follow_up.json()["override"]["version"] == 2
    assert follow_up.json()["override"]["old_status"] == "not_found"  # the human answer it replaced


def test_stale_expected_version_is_a_409_with_details(api, db):
    company = make_company(db)
    correct(api, company.id, new_status="yes", expected=0)
    r = correct(api, company.id, new_status="possible", expected=0)  # this screen still showed version 0
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "VERSION_CONFLICT"
    assert err["details"]["current_version"] == 1
    assert err["details"]["changed_by"] == "reviewer@test.local"
    assert err["details"]["current_status"] == "yes"
    assert err["details"]["changed_at"]
    assert db.scalar(select(func.count()).select_from(Override)) == 1  # nothing overwritten


def test_null_removes_the_correction_and_history_is_newest_first(api, db):
    company = make_company(db)
    scan(db, company, {"grain": "yes"})
    correct(api, company.id, new_status="not_found", expected=0, reason="first look")
    removed = correct(api, company.id, new_status=None, expected=1, reason="was wrong, back to automated")
    assert removed.status_code == 201
    assert removed.json()["answer"]["status"] == "yes" and removed.json()["answer"]["provenance"] == "site"

    history = api.get(f"/api/companies/{company.id}/overrides").json()["items"]
    assert [(h["version"], h["old_status"], h["new_status"]) for h in history] == [
        (2, "not_found", None), (1, "yes", "not_found")]
    assert history[0]["reviewer_email"] == "reviewer@test.local"

    nothing = correct(api, company.id, new_status=None, expected=2)
    assert nothing.status_code == 422 and nothing.json()["error"]["code"] == "NOTHING_TO_REMOVE"


def test_accounting_can_be_corrected_by_a_human(api, db):
    company = make_company(db)
    scan(db, company, {"accounting": "yes"})
    r = correct(api, company.id, category="accounting", new_status="not_found", reason="no bookkeeping service")
    assert r.status_code == 201
    answer = final_answers(db, company.id)["accounting"]
    assert (answer["status"], answer["provenance"]) == ("not_found", "human")
    assert answer["automated"]["provenance"] == "rule"  # the rule's answer is kept alongside


def test_reason_is_required(api, db):
    r = correct(api, make_company(db).id, reason="")
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_two_reviewers_racing_on_the_same_version_exactly_one_wins(fresh_db):
    """Scenario G: two sessions save a correction for the same answer at the same instant, both based on version 0."""
    with fresh_db() as s:
        company = make_company(s)
        reviewers = [User(email=f"r{i}@test.local", password_hash="x", role="reviewer") for i in (1, 2)]
        s.add_all(reviewers)
        s.commit()
        company_id, reviewer_ids = company.id, [r.id for r in reviewers]

    start = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def save(i, new_status):
        with fresh_db() as s:
            reviewer = s.get(User, reviewer_ids[i])
            start.wait()  # both go at once
            try:
                row = create_override(s, company_id, "grain", new_status, f"reviewer {i + 1} says {new_status}", 0,
                                      reviewer)
                outcomes[reviewer.email] = f"saved version {row.version}"
            except ApiError as exc:
                d = exc.details
                outcomes[reviewer.email] = (f"{exc.status} {exc.code} (current_version={d['current_version']}, "
                                            f"changed_by={d['changed_by']})")

    threads = [threading.Thread(target=save, args=(0, "yes")), threading.Thread(target=save, args=(1, "not_found"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)

    print("\nSCENARIO G outcomes:", outcomes)  # shown with pytest -s (saved as evidence)
    results = sorted(outcomes.values())
    assert sum(r.startswith("saved version 1") for r in results) == 1
    assert sum(r.startswith("409 VERSION_CONFLICT") for r in results) == 1
    with fresh_db() as s:
        rows = s.scalars(select(Override).where(Override.company_id == company_id)).all()
        print("SCENARIO G override rows:", [(o.version, o.new_status, o.reviewer_id) for o in rows])
        assert len(rows) == 1 and rows[0].version == 1


def test_race_lost_at_insert_is_caught_by_the_unique_rule(db, monkeypatch):
    """Forces the worst timing: reviewer 2 READ 'no correction yet' just before reviewer 1 saved version 1.
    The version check passes for reviewer 2, so only the UNIQUE (company, category, version) rule stops it."""
    from app.services import overrides as service

    company = make_company(db)
    r1, r2 = (User(email=f"race{i}@test.local", password_hash="x", role="reviewer") for i in (1, 2))
    db.add_all([r1, r2])
    db.flush()
    create_override(db, company.id, "grain", "yes", "reviewer 1 was first", 0, r1)

    real_latest = service.latest_override
    calls = {"n": 0}

    def stale_first_read(*args):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_latest(*args)  # 1st read is stale, later reads are real

    monkeypatch.setattr(service, "latest_override", stale_first_read)
    with pytest.raises(ApiError) as err:
        create_override(db, company.id, "grain", "not_found", "reviewer 2, stale screen", 0, r2)
    assert (err.value.status, err.value.code) == (409, "VERSION_CONFLICT")
    assert err.value.details["changed_by"] == "race1@test.local"
    rows = db.scalars(select(Override).where(Override.company_id == company.id)).all()
    assert [(o.version, o.new_status) for o in rows] == [(1, "yes")]


def test_scenario_e_new_scan_disagrees_human_answer_stays(db, monkeypatch, crawler_settings):
    """Scenario E: a human corrected 'feed' to yes; a later automated scan says not_found."""
    from app.classifier import pipeline
    from app.classifier.pipeline import classify_job
    from tests.test_classify_pipeline import FakeModel, make_job, output, use_models

    crawler_settings(ai_provider="google", ai_fallback_providers="", google_api_key="k", google_model="m")
    monkeypatch.setattr(pipeline, "sleep", lambda s: None)
    job = make_job(db, ["We buy grain at our elevators and post daily cash bids.\n"
                        "Propane and diesel delivery for farms and homes."])
    reviewer = User(email="human@test.local", password_hash="x", role="reviewer")
    db.add(reviewer)
    db.flush()
    db.add(Override(company_id=job.company_id, category="feed", old_status=None, new_status="yes",
                    reason="they run a feed mill (phone call)", reviewer_id=reviewer.id, version=1))
    db.commit()

    def nf(category):
        return {"category": category, "status": "not_found", "explanation": "not on the site", "evidence": []}

    answer = output(db, job.id, {c: nf(c) for c in ("agronomy", "grain", "energy", "feed", "gas_station",
                                                     "retail_store")})
    use_models(monkeypatch, google=FakeModel(answer))
    classify_job(db, job.id)

    new_feed = db.scalar(select(Classification).where(Classification.job_id == job.id,
                                                      Classification.category == "feed"))
    assert new_feed.status == "not_found" and new_feed.conflicts_with_override is True
    job.status, job.finished_at = "completed", datetime.now(UTC)
    db.flush()
    final = final_answers(db, job.company_id)["feed"]
    assert (final["status"], final["provenance"], final["conflict"]) == ("yes", "human", True)
    override = db.scalar(select(Override).where(Override.company_id == job.company_id))
    assert (override.version, override.new_status, override.reason) == (1, "yes", "they run a feed mill (phone call)")


@pytest.mark.parametrize("bad", [{"new_status": "maybe"}, {"category": "bakery"}, {"expected_version": -1}])
def test_bad_correction_input_is_422(api, db, bad):
    body = {"category": "grain", "new_status": "yes", "reason": "checked", "expected_version": 0, **bad}
    r = api.post(f"/api/companies/{make_company(db).id}/overrides", json=body)
    assert r.status_code == 422
