"""Stay logged in across a browser refresh: the login token (JWT) is kept in a browser cookie.

- Cookie `bep_token`: Path=/, SameSite=Strict, Secure when the page is served over https, Max-Age = the token's
  lifetime (expires_in from the login answer, 8 h). The token is NEVER put in the URL or query parameters.
- Read: `st.context.cookies` - the cookies the browser sent when this page (session) was opened. A refresh opens
  a new session, so the cookie is there on its first run.
- Write / delete: extra-streamlit-components' CookieManager, a tiny JavaScript component that sets
  `document.cookie` in the browser.
- Login / logout only QUEUE the change (session_state["cookie_pending"]); app.py applies it on the next normal
  run with apply_pending(). Reason: login and logout call st.rerun() right away, which would remove the cookie
  component before its JavaScript has run.

Trade-off (also in docs/design.md): a cookie set by page JavaScript cannot be HttpOnly, so a script running on
this page could read it. Mitigated by the short expiry, Secure, SameSite=Strict and no tokens in URLs;
Streamlit renders website text as text (we escape everything we put into HTML). A production app would use an
HttpOnly session cookie set by the server.
"""
from datetime import datetime, timedelta

import streamlit as st

COOKIE = "bep_token"
PENDING = "cookie_pending"  # ("save", token, max_age) or ("delete",)


def read_token() -> str | None:
    """The token cookie the browser sent with this page load, if any."""
    try:
        return st.context.cookies.get(COOKIE) or None
    except (AttributeError, RuntimeError):  # no browser context (e.g. bare script runs)
        return None


def _is_https() -> bool:
    try:
        url = getattr(st.context, "url", None) or ""
        proto = st.context.headers.get("X-Forwarded-Proto", "")  # Render's proxy terminates TLS
        return url.startswith("https://") or proto == "https"
    except (AttributeError, RuntimeError):
        return False


def save_token(token: str, max_age: int) -> None:
    import extra_streamlit_components as stx  # imported here: only needed when a cookie is written

    stx.CookieManager(key="bep_cookie_init").set(
        COOKIE, token, key="bep_cookie_set", path="/", max_age=max_age,
        expires_at=datetime.now() + timedelta(seconds=max_age), secure=_is_https(), same_site="strict")


def delete_token() -> None:
    import extra_streamlit_components as stx

    try:
        stx.CookieManager(key="bep_cookie_init").delete(COOKIE, key="bep_cookie_delete")
    except KeyError:  # the component didn't know the cookie yet: the delete was still sent to the browser
        pass


def queue_save(token: str, max_age: int) -> None:
    st.session_state[PENDING] = ("save", token, max_age)


def queue_delete() -> None:
    st.session_state[PENDING] = ("delete",)


def apply_pending() -> None:
    """Write / delete the cookie if login or logout asked for it (called once per run by app.py)."""
    pending = st.session_state.pop(PENDING, None)
    if not pending:
        return
    if pending[0] == "save":
        save_token(pending[1], pending[2])
    else:
        delete_token()
