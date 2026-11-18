import os
import sys
from types import SimpleNamespace

import pytest

# Let pages import `api_client` the same way they do when Streamlit runs them.
FRONTEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, FRONTEND_DIR)
os.chdir(FRONTEND_DIR)


@pytest.fixture(autouse=True)
def browser_cookie(monkeypatch):
    """A fake browser cookie jar for every UI test (AppTest has no browser, so it can't seed or keep cookies).

    browser_cookie.jar["bep_token"] = "..."  -> the browser "sends" that cookie when a page is opened;
    save_token / delete_token change the jar like the real CookieManager would, and are recorded in .log.
    """
    import browser_session

    fake = SimpleNamespace(jar={}, log=[])

    def save(token, max_age):
        fake.jar[browser_session.COOKIE] = token
        fake.log.append(("save", token, max_age))

    def delete():
        fake.jar.pop(browser_session.COOKIE, None)
        fake.log.append(("delete",))

    monkeypatch.setattr(browser_session, "read_token", lambda: fake.jar.get(browser_session.COOKIE))
    monkeypatch.setattr(browser_session, "save_token", save)
    monkeypatch.setattr(browser_session, "delete_token", delete)
    return fake
