"""Login, companies, company detail, runs, and session expiry (backend faked with respx)."""
import respx

from api_client import API_URL, SESSION_EXPIRED
from tests.helpers import REVIEWER, VIEWER, company_detail_body, page, texts

# ------------------------------------------------------------------ login

@respx.mock
def test_login_success_stores_the_token():
    respx.post(f"{API_URL}/api/auth/login").respond(200, json={
        "access_token": "abc.def.ghi", "token_type": "bearer", "expires_in": 28800, "user": REVIEWER})
    at = page("../views/login.py").run()
    at.text_input[0].input("reviewer@demo.local")
    at.text_input[1].input("secret")
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state["token"] == "abc.def.ghi"
    assert at.session_state["user"]["role"] == "reviewer"


@respx.mock
def test_login_failure_shows_the_error():
    respx.post(f"{API_URL}/api/auth/login").respond(401, json={"error": {
        "code": "UNAUTHORIZED", "message": "Invalid email or password.", "details": {}}})
    at = page("../views/login.py").run()
    at.text_input[0].input("reviewer@demo.local")
    at.text_input[1].input("wrong")
    at.button[0].click().run()
    assert "Invalid email or password." in at.error[0].value
    assert "token" not in at.session_state


# ------------------------------------------------------------------ companies

def companies_body(items):
    return {"items": items, "page": 1, "page_size": 25, "total": len(items)}


@respx.mock
def test_companies_page_shows_rows():
    answers = {c: {"status": "yes" if c == "grain" else None, "provenance": "site" if c == "grain" else None,
                   "conflict": False} for c in ("accounting", "agronomy", "grain", "energy", "feed", "gas_station",
                                                 "retail_store")}
    item = {"id": 7, "name": "Prairie Co-op", "website_url": "https://coop.example/", "canonical_domain": "coop.example",
            "created_at": "2026-11-18T07:00:00+00:00", "answers": answers,
            "latest_job": {"id": 3, "status": "completed"}, "last_scanned_at": "2026-11-18T07:55:00+00:00"}
    respx.get(f"{API_URL}/api/companies").respond(200, json=companies_body([item]))
    at = page("../views/companies.py", VIEWER).run()
    assert not at.exception
    table = at.dataframe[0].value
    assert list(table["name"]) == ["Prairie Co-op"]
    assert list(table["Grain"]) == ["Yes"] and list(table["Energy"]) == ["Not scanned"]


@respx.mock
def test_test_data_is_badged_and_can_be_hidden():
    answers = {c: {"status": None, "provenance": None, "conflict": False}
               for c in ("accounting", "agronomy", "grain", "energy", "feed", "gas_station", "retail_store")}
    item = {"id": 9, "name": "Clear Co-op (fixture)", "website_url": "http://clear-coop.fixture.test/",
            "canonical_domain": "clear-coop.fixture.test", "source": "fixture", "is_test_data": True,
            "created_at": "2026-11-18T07:00:00+00:00", "answers": answers, "latest_job": None, "last_scanned_at": None}
    route = respx.get(f"{API_URL}/api/companies").respond(200, json=companies_body([item]))
    at = page("../views/companies.py", VIEWER).run()
    assert list(at.dataframe[0].value["data"]) == ["Test data"]
    assert "include_test" not in str(route.calls.last.request.url)  # shown by default
    at.checkbox[0].check().run()
    assert "include_test=false" in str(route.calls.last.request.url)


@respx.mock
def test_companies_page_empty_state():
    respx.get(f"{API_URL}/api/companies").respond(200, json=companies_body([]))
    at = page("../views/companies.py", VIEWER).run()
    assert "No companies yet" in at.info[0].value


# ------------------------------------------------------------------ company detail

def mock_detail():
    respx.get(f"{API_URL}/api/companies/7").respond(200, json=company_detail_body())
    respx.get(f"{API_URL}/api/companies/7/overrides").respond(200, json={"items": []})


@respx.mock
def test_detail_shows_evidence_sources_and_conflict():
    mock_detail()
    at = page("../views/company_detail.py", VIEWER, company_id=7).run()
    assert not at.exception
    shown = texts(at)
    assert "We buy grain at our elevators." in shown
    assert "https://coop.example/grain" in shown
    assert 'bep-site">Website' in shown and 'bep-rule">Rule' in shown and 'bep-human">Human' in shown
    assert "Conflicts with the latest automated scan" in shown
    assert 'bep-notscanned">Not scanned' in shown  # never-scanned is NOT "Not found"


@respx.mock
def test_detail_escapes_website_text():
    """A quote is untrusted website text: it must be shown as text, never as HTML."""
    body = company_detail_body()
    grain = next(a for a in body["answers"] if a["category"] == "grain")
    grain["automated"]["evidence"][0]["quote"] = '<img src=x onerror="alert(1)"> We buy grain.'
    respx.get(f"{API_URL}/api/companies/7").respond(200, json=body)
    respx.get(f"{API_URL}/api/companies/7/overrides").respond(200, json={"items": []})
    shown = texts(page("../views/company_detail.py", VIEWER, company_id=7).run())
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; We buy grain." in shown
    assert "<img src=x" not in shown


@respx.mock
def test_correction_form_hidden_for_viewer_shown_for_reviewer():
    mock_detail()
    viewer = page("../views/company_detail.py", VIEWER, company_id=7).run()
    assert len(viewer.text_area) == 0
    reviewer = page("../views/company_detail.py", REVIEWER, company_id=7).run()
    assert len(reviewer.text_area) == 7  # one correction form per category


@respx.mock
def test_version_conflict_shows_someone_else_changed_it():
    mock_detail()
    route = respx.post(f"{API_URL}/api/companies/7/overrides").respond(409, json={"error": {
        "code": "VERSION_CONFLICT", "message": "Someone else changed this answer after you opened it.",
        "details": {"current_version": 2, "changed_by": "other@demo.local",
                    "changed_at": "2026-11-18T08:00:00+00:00", "current_status": "possible"}}})
    at = page("../views/company_detail.py", REVIEWER, company_id=7).run()
    at.selectbox(key="new_feed").select("Possible")
    at.text_area(key="reason_feed").input("checked the price list")
    at.button(key="FormSubmitter:correct_feed-Save correction").click().run()

    sent = route.calls.last.request
    assert b'"expected_version":1' in sent.content.replace(b" ", b"")  # the version shown on screen
    assert any("Someone else changed this answer (by other@demo.local at 2026-11-18 08:00 UTC)" in e.value
               for e in at.error), [e.value for e in at.error]


# ------------------------------------------------------------------ runs

@respx.mock
def test_run_page_shows_server_progress_and_errors():
    run = {"id": 6, "status": "completed_with_errors", "total_items": 2, "policy_version": "v1",
           "idempotency_key": None, "created_at": "2026-11-18T07:54:17+00:00", "started_at": None,
           "finished_at": None, "cancel_requested_at": None, "skipped": [],
           "counts": {"queued": 0, "running": 0, "completed": 1, "review_required": 0, "failed": 1, "cancelled": 0},
           "progress": {"done": 2, "total": 2, "percent": 100.0}}
    items = [{"job_id": 1, "company_id": 1, "company_name": "Prairie Co-op", "website_url": "https://coop.example/",
              "status": "failed", "attempt_count": 3, "max_attempts": 3, "last_error_code": "AI_UNAVAILABLE",
              "last_error_message": "all AI providers failed", "next_attempt_at": None, "created_at": None,
              "started_at": None, "finished_at": "2026-11-18T08:00:00+00:00"}]
    job = {**items[0], "run_id": 6, "lease_owner": None, "lease_expires_at": None, "heartbeat_at": None,
           "classifications": 0, "attempts": [], "events": [], "pages": []}
    respx.get(f"{API_URL}/api/runs").respond(200, json={"items": [run], "page": 1, "page_size": 50, "total": 1})
    respx.get(f"{API_URL}/api/runs/6").respond(200, json=run)
    respx.get(f"{API_URL}/api/runs/6/items").respond(200, json={"items": items, "page": 1, "page_size": 200,
                                                                "total": 1})
    respx.get(f"{API_URL}/api/jobs/1").respond(200, json=job)

    at = page("../views/runs.py", REVIEWER, run_id=6).run()
    assert not at.exception
    assert at.get("progress")[0].proto.value == 100
    jobs = at.dataframe[1].value
    assert list(jobs["error"]) == ["AI_UNAVAILABLE"] and list(jobs["message"]) == ["all AI providers failed"]
    assert any(b.label == "Retry failed" for b in at.button)


# ------------------------------------------------------------------ session expiry

@respx.mock
def test_401_logs_out_and_shows_session_expired():
    respx.get(f"{API_URL}/ready").respond(200, json={"status": "ready", "database": "ok", "migration": "x"})
    respx.get(f"{API_URL}/api/metrics").respond(401, json={"error": {
        "code": "UNAUTHORIZED", "message": "Your session expired, please log in again.", "details": {}}})
    at = page("../app.py", REVIEWER).run()
    assert not at.exception
    assert "token" not in at.session_state
    assert SESSION_EXPIRED in [w.value for w in at.warning]
    assert len(at.text_input) == 2  # the login form (email + password)
