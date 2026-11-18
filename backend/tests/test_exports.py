"""Exports: CSV columns and rows, human answers marked as such, JSON with override history."""
import csv
import io
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Classification, Evidence, Override, Page, User
from app.services.answers import ALL_CATEGORIES
from tests.factories import make_company, make_run


def scanned_company(db, n, statuses):
    company = make_company(db, n)
    _, (job,) = make_run(db, [company], statuses=["completed"])
    job.finished_at = datetime.now(UTC)
    page = Page(job_id=job.id, url=f"https://coop{n}.example/grain", outcome="ok", text_content="We buy grain.")
    db.add(page)
    db.flush()
    for category, status in statuses.items():
        c = Classification(job_id=job.id, company_id=company.id, category=category, status=status,
                           provenance="rule" if category == "accounting" else "site", explanation="x",
                           policy_version="v1", model_provider=None if category == "accounting" else "google",
                           model_name="gemini-test", prompt_version="p2")
        if status == "yes" and category != "accounting":
            c.evidence = [Evidence(page_id=page.id, source_url=page.url, quote="We buy grain.", quote_verified=True)]
        db.add(c)
    db.flush()
    return company


def test_csv_has_one_row_per_company_and_all_category_columns(api, db):
    a = scanned_company(db, 1, {"accounting": "yes", "grain": "yes", "feed": "not_found"})
    make_company(db, 2)  # never scanned
    db.add(Override(company_id=a.id, category="feed", new_status="yes", reason="phoned", version=1,
                    reviewer_id=_reviewer_id(db)))
    db.flush()

    r = api.get("/api/exports?format=csv")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="companies-')
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2
    expected_cols = ["company_name", "website", "canonical_domain", "source", "last_scanned_at"] + [
        f"{c}_{f}" for c in ALL_CATEGORIES for f in ("status", "source", "evidence_url", "quote", "conflict")]
    assert list(rows[0].keys()) == expected_cols

    first = rows[0]
    assert (first["grain_status"], first["grain_source"], first["grain_quote"]) == ("yes", "site", "We buy grain.")
    assert first["grain_evidence_url"] == "https://coop1.example/grain"
    assert (first["feed_status"], first["feed_source"], first["feed_conflict"]) == ("yes", "human", "yes")
    assert (first["accounting_source"], first["energy_status"]) == ("rule", "not_scanned")
    assert rows[1]["grain_status"] == "not_scanned"


def test_csv_respects_the_filters(api, db):
    scanned_company(db, 1, {"grain": "yes"})
    scanned_company(db, 2, {"grain": "not_found"})
    rows = list(csv.DictReader(io.StringIO(api.get("/api/exports?format=csv&category=grain&status=yes").text)))
    assert [r["canonical_domain"] for r in rows] == ["coop1.example"]


def test_json_has_full_detail_and_override_history(api, db):
    a = scanned_company(db, 1, {"grain": "yes"})
    db.add(Override(company_id=a.id, category="grain", new_status="possible", reason="old page", version=1,
                    reviewer_id=_reviewer_id(db)))
    db.flush()
    r = api.get("/api/exports?format=json")
    assert r.headers["content-disposition"].endswith('.json"')
    (item,) = json.loads(r.text)
    grain = next(x for x in item["answers"] if x["category"] == "grain")
    assert grain["provenance"] == "human"
    assert grain["automated"]["evidence"][0]["quote"] == "We buy grain."
    assert grain["automated"]["model_name"] == "gemini-test" and grain["automated"]["prompt_version"] == "p2"
    assert item["override_history"][0]["reason"] == "old page"


def test_corrections_export(api, db):
    a = scanned_company(db, 1, {"grain": "yes"})
    db.add(Override(company_id=a.id, category="grain", old_status="yes", new_status=None, reason="undo",
                    version=1, reviewer_id=_reviewer_id(db)))
    db.flush()
    rows = list(csv.DictReader(io.StringIO(api.get("/api/exports/overrides?format=csv").text)))
    assert rows[0]["new_status"] == "(correction removed)" and rows[0]["reviewer_email"] == "reviewer@test.local"


def _reviewer_id(db):
    """The user the `api` fixture is logged in as."""
    return db.scalar(select(User.id).where(User.email == "reviewer@test.local"))
