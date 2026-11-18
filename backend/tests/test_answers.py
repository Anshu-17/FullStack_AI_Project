"""Final answers: the human override wins; conflicts are shown; never-scanned is null, not not_found."""
from datetime import UTC, datetime

from app.db.models import Classification, Override, User
from app.services.answers import final_answers
from tests.factories import make_company, make_run


def scanned(db, company, statuses: dict[str, str]):
    _, (job,) = make_run(db, [company], statuses=["completed"])
    job.finished_at = datetime.now(UTC)
    for category, status in statuses.items():
        db.add(Classification(job_id=job.id, company_id=company.id, category=category, status=status,
                              provenance="rule" if category == "accounting" else "site",
                              explanation=f"{category} explanation", policy_version="v1"))
    db.flush()
    return job


def override(db, company, category, new_status, version):
    user = db.query(User).first() or User(email="r@test.local", password_hash="x", role="reviewer")
    db.add(user)
    db.flush()
    db.add(Override(company_id=company.id, category=category, new_status=new_status, reason="phoned them",
                    reviewer_id=user.id, version=version))
    db.flush()


def test_never_scanned_is_null_not_not_found(db):
    answers = final_answers(db, make_company(db).id)
    assert all(a["status"] is None and a["automated"] is None for a in answers.values())


def test_override_wins_with_provenance_human_and_conflict_flag(db):
    company = make_company(db)
    scanned(db, company, {"accounting": "yes", "feed": "not_found", "grain": "yes"})
    override(db, company, "feed", "yes", 1)

    answers = final_answers(db, company.id)
    feed = answers["feed"]
    assert (feed["status"], feed["provenance"], feed["explanation"]) == ("yes", "human", "phoned them")
    assert feed["automated"]["status"] == "not_found"  # kept alongside for comparison
    assert feed["conflict"] is True
    assert answers["grain"]["provenance"] == "site" and answers["grain"]["conflict"] is False
    assert answers["accounting"]["provenance"] == "rule"
    assert answers["energy"]["status"] is None  # not in that scan


def test_removed_override_falls_back_to_the_automated_answer(db):
    company = make_company(db)
    scanned(db, company, {"feed": "not_found"})
    override(db, company, "feed", "yes", 1)
    override(db, company, "feed", None, 2)  # reviewer removed their correction
    feed = final_answers(db, company.id)["feed"]
    assert (feed["status"], feed["provenance"], feed["override_version"]) == ("not_found", "site", 2)
