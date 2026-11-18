"""The ONLY place the UI talks to the backend. Every page uses these helpers.

The UI never connects to the database directly: it calls the FastAPI backend over HTTP
and shows the JSON it gets back.

Login: the token from POST /api/auth/login is kept in st.session_state and in a browser
cookie (browser_session.py), so a page refresh keeps you logged in. It is sent as
"Authorization: Bearer <token>". If the backend answers 401 to a logged-in request (token
expired or account disabled), we log out, delete the cookie and send the user back to the
login page with a message.
"""
import os

import httpx
import streamlit as st

import browser_session

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = httpx.Timeout(15.0)
SESSION_EXPIRED = "Your session expired, please log in again."


class ApiError(Exception):
    """A problem the user should see, already turned into a readable message."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message, self.status, self.code, self.details = message, status, code, details or {}


# ------------------------------------------------------------------ session

def is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def current_user() -> dict:
    return st.session_state.get("user") or {}


def is_reviewer() -> bool:
    return current_user().get("role") == "reviewer"


def logout(message: str | None = None) -> None:
    """Forget the token and everything remembered for this session, and delete the browser cookie."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    # This session already looked at the cookie: don't log in again from the (stale) cookie the browser
    # sent when the page was opened.
    st.session_state["cookie_checked"] = True
    browser_session.queue_delete()
    if message:
        st.session_state["flash"] = message


def restore_from_cookie() -> None:
    """Once per browser session (= after every refresh): log in again with the token cookie, if valid."""
    if is_logged_in() or st.session_state.get("cookie_checked"):
        return
    st.session_state["cookie_checked"] = True
    token = browser_session.read_token()
    if not token:
        return
    try:
        with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as client:
            response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        return  # backend unreachable: show the login page; the cookie is kept for the next try
    if response.status_code == 200:
        st.session_state["token"] = token
        st.session_state["user"] = response.json()
    elif response.status_code == 401:
        logout(SESSION_EXPIRED)  # expired / revoked: delete the cookie, show the login page with a message


# ------------------------------------------------------------------ HTTP

def _headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _error_from(response: httpx.Response) -> ApiError:
    # Our API returns {"error": {"code", "message", "details"}}; fall back to FastAPI's {"detail": ...}
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") or {}
    message = error.get("message") or body.get("detail") or f"Request failed ({response.status_code})"
    return ApiError(str(message), response.status_code, error.get("code"), error.get("details"))


def _send(method: str, path: str, headers: dict | None = None, **kwargs) -> httpx.Response:
    sent_token = is_logged_in()
    try:
        with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as client:
            response = client.request(method, path, headers={**_headers(), **(headers or {})}, **kwargs)
    except httpx.ConnectError as exc:
        raise ApiError(f"Can't reach the backend at {API_URL}. Is it running?") from exc
    except httpx.TimeoutException as exc:
        raise ApiError("The backend took too long to answer. Try again.") from exc

    if response.status_code == 401 and sent_token:
        logout(SESSION_EXPIRED)
        st.rerun()  # the app starts again and shows the login page with the message
    if not response.is_success:
        raise _error_from(response)
    return response


def request(method: str, path: str, **kwargs):
    response = _send(method, path, **kwargs)
    return response.json() if response.content else None


def get(path: str, **params):
    clean = {k: v for k, v in params.items() if v not in (None, "")}  # skip empty filters
    return request("GET", path, params=clean or None)


def post(path: str, json: dict | None = None, files: dict | None = None, headers: dict | None = None):
    return request("POST", path, json=json, files=files, headers=headers)


def download(path: str, **params) -> bytes:
    """Raw bytes of a file the backend produces (CSV / JSON exports)."""
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    return _send("GET", path, params=clean or None).content


def upload_file(file_name: str, data: bytes):
    return post("/api/uploads", files={"file": (file_name, data, "text/csv")})


# ------------------------------------------------------------------ login

def login(email: str, password: str) -> dict:
    """Check the password with the backend; on success remember the token and the user."""
    body = request("POST", "/api/auth/login", json={"email": email.strip(), "password": password})
    st.session_state["token"] = body["access_token"]
    st.session_state["user"] = body["user"]
    st.session_state["cookie_checked"] = True
    st.session_state.pop("flash", None)
    browser_session.queue_save(body["access_token"], int(body.get("expires_in") or 8 * 3600))
    return body["user"]
