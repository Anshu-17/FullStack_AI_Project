"""Stay logged in across a refresh (token cookie), expired cookie -> login page, logout deletes it."""
import respx

from api_client import API_URL, SESSION_EXPIRED
from tests.helpers import REVIEWER, page
from tests.test_dashboard import METRICS, RUNS


def mock_dashboard():
    respx.get(f"{API_URL}/ready").respond(200, json={"status": "ready", "database": "ok", "migration": "x"})
    respx.get(f"{API_URL}/api/metrics").respond(200, json=METRICS)
    respx.get(f"{API_URL}/api/runs").respond(200, json=RUNS)


@respx.mock
def test_refresh_with_a_valid_cookie_stays_logged_in(browser_cookie):
    """A refresh = a NEW session (empty session_state) whose browser sends the cookie."""
    browser_cookie.jar["bep_token"] = "saved.jwt.token"
    me = respx.get(f"{API_URL}/api/auth/me").respond(200, json=REVIEWER)
    mock_dashboard()

    at = page("../app.py").run()  # no user in session_state, like after a refresh

    assert not at.exception
    assert me.calls.last.request.headers["authorization"] == "Bearer saved.jwt.token"
    assert at.session_state["token"] == "saved.jwt.token"
    assert at.session_state["user"]["role"] == "reviewer"
    assert len(at.text_input) == 0  # no login form: the dashboard is shown
    assert any(m.label == "Companies" for m in at.metric)


@respx.mock
def test_expired_cookie_goes_back_to_login_and_is_deleted(browser_cookie):
    browser_cookie.jar["bep_token"] = "expired.jwt.token"
    respx.get(f"{API_URL}/api/auth/me").respond(401, json={"error": {
        "code": "UNAUTHORIZED", "message": "Your session expired, please log in again.", "details": {}}})

    at = page("../app.py").run()

    assert not at.exception
    assert "token" not in at.session_state
    assert SESSION_EXPIRED in [w.value for w in at.warning]
    assert len(at.text_input) == 2  # the login form
    assert browser_cookie.log == [("delete",)] and "bep_token" not in browser_cookie.jar


@respx.mock
def test_logout_deletes_the_cookie_and_a_refresh_does_not_log_in_again(browser_cookie):
    browser_cookie.jar["bep_token"] = "saved.jwt.token"
    respx.get(f"{API_URL}/api/auth/me").respond(200, json=REVIEWER)
    mock_dashboard()
    at = page("../app.py").run()
    assert at.session_state["token"] == "saved.jwt.token"

    at.sidebar.button[0].click().run()  # "Log out"

    assert not at.exception
    assert "token" not in at.session_state
    assert browser_cookie.log == [("delete",)]
    assert len(at.text_input) == 2  # back on the login page
    assert page("../app.py").run().session_state["cookie_checked"]  # new session: no cookie -> stays logged out


@respx.mock
def test_login_saves_the_cookie_with_the_token_lifetime(browser_cookie):
    respx.post(f"{API_URL}/api/auth/login").respond(200, json={
        "access_token": "new.jwt.token", "token_type": "bearer", "expires_in": 28800, "user": REVIEWER})
    mock_dashboard()
    at = page("../app.py").run()
    at.text_input[0].input("reviewer@demo.local")
    at.text_input[1].input("secret")
    at.button(key="FormSubmitter:login-Log in").click().run()

    assert not at.exception
    assert browser_cookie.log == [("save", "new.jwt.token", 28800)]
    assert at.session_state["token"] == "new.jwt.token"
    assert "token=" not in str(at.query_params)  # never in the URL
