"""Shared helpers for UI tests: open a page as a given user, and canned API answers."""
from streamlit.testing.v1 import AppTest

TIMEOUT = 30  # seconds; generous so a slow, busy machine doesn't make the tests flaky

REVIEWER = {"id": 1, "email": "reviewer@demo.local", "role": "reviewer"}
VIEWER = {"id": 2, "email": "viewer@demo.local", "role": "viewer"}


def page(path: str, user: dict | None = None, **state) -> AppTest:
    """An AppTest for `path` (relative to tests/), logged in as `user` with extra session_state."""
    at = AppTest.from_file(path, default_timeout=TIMEOUT)
    if user:
        at.session_state["token"] = "test-token"
        at.session_state["user"] = user
    for key, value in state.items():
        at.session_state[key] = value
    return at


def texts(at: AppTest) -> str:
    """All visible markdown / caption / alert text of a run, joined (handy for 'is X shown?')."""
    parts = []
    for kind in ("markdown", "caption", "error", "warning", "info", "success", "title", "subheader"):
        parts += [getattr(e, "value", "") or "" for e in getattr(at, kind)]
    return "\n".join(str(p) for p in parts)


def answer(category, status, provenance, evidence=None, conflict=False, version=0, automated_status=None):
    automated = None
    if provenance in ("site", "rule") or automated_status:
        automated = {"classification_id": 1, "job_id": 1, "status": automated_status or status,
                     "provenance": "rule" if category == "accounting" else "site",
                     "explanation": "from the website", "confidence": 0.9, "model_provider": "google",
                     "model_name": "gemini-2.5-flash", "prompt_version": "p2", "policy_version": "v1",
                     "conflicts_with_override_at_scan": conflict, "created_at": "2026-11-18T07:55:00+00:00",
                     "evidence": evidence or []}
    return {"category": category, "status": status, "provenance": provenance,
            "explanation": "phoned them" if provenance == "human" else "from the website",
            "automated": automated, "override": None, "version": version, "conflict": conflict}


def company_detail_body():
    grain_quote = {"quote": "We buy grain at our elevators.", "source_url": "https://coop.example/grain",
                   "quote_verified": True, "page_id": 1, "fetched_at": "2026-11-18T07:54:00+00:00"}
    answers = [answer("accounting", "yes", "rule")]
    answers.append(answer("agronomy", "not_found", "site"))
    answers.append(answer("grain", "yes", "site", evidence=[grain_quote]))
    answers.append(answer("energy", None, None))
    answers.append(answer("feed", "yes", "human", conflict=True, version=1, automated_status="not_found"))
    answers.append(answer("gas_station", "possible", "site"))
    answers.append(answer("retail_store", "not_found", "site"))
    return {"id": 7, "name": "Prairie Co-op", "website_url": "https://coop.example/", "canonical_domain": "coop.example",
            "created_at": "2026-11-18T07:00:00+00:00", "answers": answers,
            "scan_history": [{"id": 3, "run_id": 2, "status": "review_required", "attempt_count": 1,
                              "last_error_code": None, "created_at": "2026-11-18T07:50:00+00:00",
                              "started_at": "2026-11-18T07:50:00+00:00", "finished_at": "2026-11-18T07:55:00+00:00"}]}
