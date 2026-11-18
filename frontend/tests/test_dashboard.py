"""UI tests: the dashboard shows what the backend returns, and a clear error when it's down.

The backend is faked with respx, so these tests don't need FastAPI running.
"""
import httpx
import respx
from streamlit.testing.v1 import AppTest

from api_client import API_URL

STATS = {
    "companies": 3,
    "runs": 1,
    "jobs": {"queued": 1, "running": 1, "completed": 1, "review_required": 0, "failed": 0, "cancelled": 0},
    "classifications": 7,
    "overrides": 0,
}


@respx.mock
def test_dashboard_shows_backend_counts():
    respx.get(f"{API_URL}/ready").mock(
        return_value=httpx.Response(200, json={"status": "ready", "database": "ok", "migration": "abc123"})
    )
    respx.get(f"{API_URL}/api/stats").mock(return_value=httpx.Response(200, json=STATS))

    at = AppTest.from_file("../views/dashboard.py", default_timeout=10).run()

    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Companies"] == "3"
    assert metrics["Answers saved"] == "7"
    assert "abc123" in at.success[0].value


@respx.mock
def test_dashboard_explains_when_backend_is_down():
    respx.get(f"{API_URL}/ready").mock(side_effect=httpx.ConnectError("refused"))

    at = AppTest.from_file("../views/dashboard.py", default_timeout=10).run()

    assert not at.exception
    assert "Can't reach the backend" in at.error[0].value
