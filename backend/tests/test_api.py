"""API shapes: lists, errors, uploads, companies, metrics."""
from app.db.models import AIUsage
from tests.factories import make_company, make_run


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


def test_list_shape_and_paging(api, db):
    for n in range(1, 6):
        make_company(db, n)
    body = api.get("/api/companies?page=2&page_size=2").json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert (body["page"], body["page_size"], body["total"], len(body["items"])) == (2, 2, 5, 2)


def test_page_size_limit_is_a_validation_error(api):
    err = assert_error(api.get("/api/companies?page_size=500"), 422, "VALIDATION_ERROR")
    assert err["details"]["fields"][0]["field"] == "query.page_size"


def test_not_found_shapes(api):
    assert_error(api.get("/api/companies/999"), 404, "NOT_FOUND")
    assert_error(api.get("/api/runs/999"), 404, "NOT_FOUND")
    assert_error(api.get("/api/no-such-route"), 404, "NOT_FOUND")


def test_validation_error_lists_the_bad_fields(api):
    err = assert_error(api.post("/api/companies", json={"name": "X"}), 422, "VALIDATION_ERROR")
    assert any(f["field"] == "body.website" for f in err["details"]["fields"])


def test_upload_returns_counts_and_only_problem_rows(api):
    csv = b"company_name,website\nA,a.example\nB,b.example\nA again,a.example\nBad,nope\n"
    r = api.post("/api/uploads", files={"file": ("companies.csv", csv, "text/csv")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["counts"] == {"total": 4, "accepted": 2, "existing": 0, "duplicate": 1, "invalid": 1}
    assert [(row["row_no"], row["result"]) for row in body["rows"]] == [(3, "duplicate"), (4, "invalid")]

    page = api.get(f"/api/uploads/{body['upload_id']}/rows?result=accepted").json()
    assert page["total"] == 2


def test_upload_with_wrong_columns_is_400(api):
    err = assert_error(api.post("/api/uploads", files={"file": ("x.csv", b"name,url\nA,a.example\n")}),
                       400, "MISSING_COLUMNS")
    assert "company_name" in err["message"]


def test_add_company_201_then_200(api):
    first = api.post("/api/companies", json={"name": "Prairie", "website": "prairie.example"})
    again = api.post("/api/companies", json={"name": "Prairie Co-op", "website": "https://www.prairie.example/"})
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["company"]["id"] == again.json()["company"]["id"]
    assert_error(api.post("/api/companies", json={"name": "Bad", "website": "not a site"}), 422, "VALIDATION_ERROR")


def test_company_detail_unscanned_answers_are_null(api, db):
    company = make_company(db)
    body = api.get(f"/api/companies/{company.id}").json()
    assert len(body["answers"]) == 7
    assert all(a["status"] is None and a["explanation"] == "Not scanned yet." for a in body["answers"])
    assert body["scan_history"] == []


def test_metrics(api, db):
    company = make_company(db)
    _, (job,) = make_run(db, [company], statuses=["failed"], attempt_count=3)
    db.add(AIUsage(job_id=job.id, provider="google", model="m", input_tokens=10, output_tokens=5, outcome="ok"))
    db.add(AIUsage(job_id=job.id, provider="google", model="m", outcome="timeout", error_code="AI_TIMEOUT"))
    db.flush()
    body = api.get("/api/metrics").json()
    assert body["jobs"]["failed"] == 1
    assert body["retries"] == 2
    assert body["ai_calls"] == {"google": {"ok": 1, "timeout": 1}}
    assert body["ai_tokens"] == {"input": 10, "output": 5}
    assert body["est_cost_usd"] is None  # no prices -> unknown, not 0
    assert api.get("/api/stats").status_code == 200  # old endpoint still works
