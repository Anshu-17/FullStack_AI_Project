"""The only place the UI talks to the backend. Every page uses these helpers.

The UI never connects to the database directly: it calls the FastAPI backend
over HTTP and shows the JSON it gets back.
"""
import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = httpx.Timeout(15.0)


class ApiError(Exception):
    """A problem the user should see, already turned into a readable message."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def _headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _handle(response: httpx.Response):
    if response.is_success:
        return response.json() if response.content else None
    # Our API returns {"error": {"code", "message"}}; fall back to FastAPI's {"detail": ...}
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") or {}
    message = error.get("message") or body.get("detail") or f"Request failed ({response.status_code})"
    raise ApiError(str(message), response.status_code)


def request(method: str, path: str, **kwargs):
    try:
        with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as client:
            response = client.request(method, path, headers=_headers(), **kwargs)
    except httpx.ConnectError as exc:
        raise ApiError(f"Can't reach the backend at {API_URL}. Is it running?") from exc
    except httpx.TimeoutException as exc:
        raise ApiError("The backend took too long to answer. Try again.") from exc
    return _handle(response)


def get(path: str, **params):
    return request("GET", path, params=params or None)


def post(path: str, json: dict | None = None, files: dict | None = None):
    return request("POST", path, json=json, files=files)
