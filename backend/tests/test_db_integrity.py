"""The database itself must refuse bad or duplicate data (scenarios A, C, E, G).

These rules are enforced by constraints, so they hold even if two requests or
two workers race each other - not just when application code remembers to check.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Classification,
    Company,
    Job,
    Override,
    PolicyVersion,
    Run,
    User,
)


@pytest.fixture()
def base(db):
    """Minimal rows most tests need: a policy, a reviewer, a company, a run, a job."""
    policy = PolicyVersion(version="t1", description="test policy", rules={}, is_active=True)
    user = User(email="r@test.local", password_hash="x", role="reviewer")
    company = Company(
        name="Prairie Co-op", website_url="https://prairiecoop.example/", canonical_domain="prairiecoop.example"
    )
    db.add_all([policy, user, company])
    db.flush()
    run = Run(created_by=user.id, policy_version="t1")
    db.add(run)
    db.flush()
    job = Job(run_id=run.id, company_id=company.id)
    db.add(job)
    db.flush()
    return {"policy": policy, "user": user, "company": company, "run": run, "job": job}


def expect_integrity_error(db, *rows):
    """Insert rows inside a savepoint and assert the database rejects them."""
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add_all(rows)
        db.flush()


def test_same_website_cannot_be_stored_twice(db, base):
    dup = Company(
        name="Prairie Coop (again)", website_url="http://prairiecoop.example", canonical_domain="prairiecoop.example"
    )
    expect_integrity_error(db, dup)


def test_one_job_per_company_per_run(db, base):
    second = Job(run_id=base["run"].id, company_id=base["company"].id)
    expect_integrity_error(db, second)


def test_one_answer_per_category_per_job(db, base):
    def answer():
        return Classification(
            job_id=base["job"].id, company_id=base["company"].id, category="grain",
            status="yes", provenance="site", explanation="cash bids", policy_version="t1",
        )
    db.add(answer())
    db.flush()
    expect_integrity_error(db, answer())


def test_run_idempotency_key_is_unique(db, base):
    db.add(Run(created_by=base["user"].id, policy_version="t1", idempotency_key="abc"))
    db.flush()
    expect_integrity_error(db, Run(created_by=base["user"].id, policy_version="t1", idempotency_key="abc"))


def test_two_reviewers_cannot_both_save_the_same_override_version(db, base):
    """Optimistic locking: both reviewers saw version 0 and try to write version 1."""
    def override(new_status):
        return Override(
            company_id=base["company"].id, category="grain", old_status="yes",
            new_status=new_status, reason="checked the site", reviewer_id=base["user"].id, version=1,
        )
    db.add(override("possible"))
    db.flush()
    expect_integrity_error(db, override("not_found"))


@pytest.mark.parametrize(
    "field,bad_value",
    [("category", "bakery"), ("status", "maybe"), ("provenance", "guess")],
)
def test_classification_rejects_values_outside_the_taxonomy(db, base, field, bad_value):
    values = dict(
        job_id=base["job"].id, company_id=base["company"].id, category="feed",
        status="yes", provenance="site", explanation="x", policy_version="t1",
    )
    values[field] = bad_value
    expect_integrity_error(db, Classification(**values))


def test_job_status_must_be_known(db, base):
    expect_integrity_error(db, Job(run_id=base["run"].id, company_id=base["company"].id, status="done-ish"))


def test_user_role_must_be_known(db):
    expect_integrity_error(db, User(email="x@test.local", password_hash="x", role="superuser"))
