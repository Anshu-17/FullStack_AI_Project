"""Dashboard: shows what the backend returns, and a clear error when it's down (backend faked with respx)."""
import httpx
import respx

from api_client import API_URL
from tests.helpers import REVIEWER, page

METRICS = {
    "companies": 3, "runs": 1, "classifications": 7, "overrides": 0,
    "jobs": {"queued": 1, "running": 1, "completed": 1, "review_required": 0, "failed": 0, "cancelled": 0},
    "retries": 2, "job_duration_seconds": {"avg": 41.5, "median": 40.0},
    "ai_calls": {"google": {"ok": 3, "timeout": 1}}, "ai_tokens": {"input": 12000, "output": 9000},
    "est_cost_usd": None, "ai_calls_without_cost": 4,
}
RUNS = {"items": [{"id": 6, "status": "completed", "progress": {"done": 2, "total": 2, "percent": 100.0},
                   "created_at": "2026-11-18T07:54:17+00:00"}], "page": 1, "page_size": 5, "total": 1}


@respx.mock
def test_dashboard_shows_backend_metrics_and_recent_runs():
    respx.get(f"{API_URL}/ready").respond(200, json={"status": "ready", "database": "ok", "migration": "abc123"})
    respx.get(f"{API_URL}/api/metrics").respond(200, json=METRICS)
    respx.get(f"{API_URL}/api/runs").respond(200, json=RUNS)

    at = page("../views/dashboard.py", REVIEWER).run()

    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Companies"] == "3"
    assert metrics["Answers saved"] == "7"
    assert metrics["Retries"] == "2"
    assert metrics["Estimated AI cost"] == "unknown"  # no prices -> never a made-up number
    assert "abc123" in at.success[0].value
    assert respx.calls.last.request.headers["authorization"] == "Bearer test-token"


@respx.mock
def test_dashboard_explains_when_backend_is_down():
    respx.get(f"{API_URL}/ready").mock(side_effect=httpx.ConnectError("refused"))
    at = page("../views/dashboard.py", REVIEWER).run()
    assert not at.exception
    assert "Can't reach the backend" in at.error[0].value
