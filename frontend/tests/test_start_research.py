"""Starting research straight from the UI: after adding a company, on the detail page, and for all
never-researched companies (backend faked with respx)."""
import json

import respx

from api_client import API_URL
from tests.helpers import REVIEWER, VIEWER, company_detail_body, page, texts

ANSWERS = {c: {"status": None, "provenance": None, "conflict": False}
           for c in ("accounting", "agronomy", "grain", "energy", "feed", "gas_station", "retail_store")}


def run_body(run_id=12, created=True):
    return {"run_id": run_id, "status": "queued", "total_items": 1, "skipped": [], "created": created}


def add_one(at):
    at.text_input[0].input("Prairie Co-op")
    at.text_input[1].input("https://coop.example")
    at.button(key="FormSubmitter:single-Add company").click().run()
    return at


# ------------------------------------------------------------------ after adding one company

@respx.mock
def test_start_research_after_adding_a_company_reuses_one_idempotency_key():
    respx.post(f"{API_URL}/api/companies").respond(201, json={"created": True, "company": {
        "id": 7, "name": "Prairie Co-op", "canonical_domain": "coop.example"}})
    runs = respx.post(f"{API_URL}/api/runs").mock(side_effect=[
        respx.MockResponse(201, json=run_body()), respx.MockResponse(200, json=run_body(created=False))])

    at = add_one(page("../views/add_companies.py", REVIEWER).run())
    assert not at.exception
    assert "Created **Prairie Co-op**" in texts(at)

    at.button(key="start_single").click().run()
    first = runs.calls.last.request
    assert json.loads(first.content) == {"company_ids": [7]}
    assert "Run **#12** started for 1 company." in texts(at)
    assert any(b.label == "Open run #12" for b in at.button)

    at.button(key="start_single").click().run()  # a second click: same key -> same run
    assert runs.calls.last.request.headers["Idempotency-Key"] == first.headers["Idempotency-Key"]
    assert "same run" in texts(at)


@respx.mock
def test_start_research_shows_already_in_progress():
    respx.post(f"{API_URL}/api/companies").respond(200, json={"created": False, "company": {
        "id": 7, "name": "Prairie Co-op", "canonical_domain": "coop.example"}})
    respx.post(f"{API_URL}/api/runs").respond(409, json={"error": {
        "code": "NOTHING_TO_RUN", "message": "None of the requested companies can be started.",
        "details": {"skipped": [{"company_id": 7, "reason": "already_in_progress"}]}}})

    at = add_one(page("../views/add_companies.py", REVIEWER).run())
    at.button(key="start_single").click().run()
    assert not at.exception
    warning = at.warning[0].value
    assert "None of the requested companies can be started." in warning and "already in progress" in warning


# ------------------------------------------------------------------ company detail

@respx.mock
def test_detail_shows_start_research_when_never_scanned_and_rescan_otherwise():
    never = {**company_detail_body(), "scan_history": []}
    respx.get(f"{API_URL}/api/companies/7").mock(side_effect=[
        respx.MockResponse(200, json=never), respx.MockResponse(200, json=never),
        respx.MockResponse(200, json=company_detail_body())])
    respx.get(f"{API_URL}/api/companies/7/overrides").respond(200, json={"items": []})
    runs = respx.post(f"{API_URL}/api/runs").respond(201, json=run_body(run_id=13))

    at = page("../views/company_detail.py", REVIEWER, company_id=7).run()
    assert at.button(key="rescan").label == "Start research"
    at.button(key="rescan").click().run()
    assert json.loads(runs.calls.last.request.content) == {"company_ids": [7]}
    assert "Run **#13** started" in texts(at)

    scanned = page("../views/company_detail.py", REVIEWER, company_id=7).run()
    assert scanned.button(key="rescan").label == "Rescan this company"


@respx.mock
def test_detail_has_no_research_button_for_viewer():
    respx.get(f"{API_URL}/api/companies/7").respond(200, json=company_detail_body())
    respx.get(f"{API_URL}/api/companies/7/overrides").respond(200, json={"items": []})
    at = page("../views/company_detail.py", VIEWER, company_id=7).run()
    assert not any(b.key == "rescan" for b in at.button)


# ------------------------------------------------------------------ companies page

def company(cid, latest_job):
    return {"id": cid, "name": f"Co {cid}", "website_url": f"https://co{cid}.example/",
            "canonical_domain": f"co{cid}.example", "created_at": "2026-11-18T07:00:00+00:00",
            "answers": ANSWERS, "latest_job": latest_job, "last_scanned_at": None}


@respx.mock
def test_start_research_for_all_not_scanned_companies():
    items = [company(1, None), company(2, {"id": 5, "status": "completed"}), company(3, None)]
    respx.get(f"{API_URL}/api/companies").respond(200, json={"items": items, "page": 1, "page_size": 25,
                                                             "total": 3})
    runs = respx.post(f"{API_URL}/api/runs").respond(201, json={**run_body(run_id=14), "total_items": 2})

    viewer = page("../views/companies.py", VIEWER).run()
    assert not any(b.key == "start_all" for b in viewer.button)  # reviewers only

    at = page("../views/companies.py", REVIEWER).run()
    at.button(key="start_all").click().run()
    assert not at.exception
    sent = runs.calls.last.request
    assert json.loads(sent.content) == {"company_ids": [1, 3]}  # only never-researched companies
    assert sent.headers["Idempotency-Key"].startswith("batch-")
    assert "Run **#14** started for 2 companies." in texts(at)
