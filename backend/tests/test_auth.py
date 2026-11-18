"""Login, tokens, roles and the login rate limit."""
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.db.models import User
from app.ratelimit import limiter
from app.security import hash_password
from tests.factories import make_company


@pytest.fixture()
def users(db):
    reviewer = User(email="Reviewer@Test.local", password_hash=hash_password("rev-pass-123"), role="reviewer")
    viewer = User(email="viewer@test.local", password_hash=hash_password("view-pass-123"), role="viewer")
    gone = User(email="gone@test.local", password_hash=hash_password("gone-pass-123"), role="reviewer",
                is_active=False)
    db.add_all([reviewer, viewer, gone])
    db.flush()
    return {"reviewer": reviewer, "viewer": viewer}


def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_a_token_and_the_user(anon_api, users):
    r = login(anon_api, "reviewer@test.local", "rev-pass-123")  # email is case-insensitive
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == settings.jwt_expires_minutes * 60
    assert body["user"] == {"id": users["reviewer"].id, "email": "Reviewer@Test.local", "role": "reviewer"}
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == str(users["reviewer"].id) and claims["role"] == "reviewer"
    assert anon_api.get("/api/auth/me", headers=auth(body["access_token"])).json()["role"] == "reviewer"


def test_wrong_password_and_unknown_email_get_the_same_answer(anon_api, users):
    wrong_password = login(anon_api, "viewer@test.local", "nope")
    unknown_email = login(anon_api, "nobody@test.local", "nope")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["message"] == "Invalid email or password."


def test_inactive_user_cannot_log_in(anon_api, users):
    assert login(anon_api, "gone@test.local", "gone-pass-123").status_code == 401


@pytest.mark.parametrize("token_kind", ["missing", "garbage", "expired", "wrong_secret"])
def test_reads_need_a_valid_token(anon_api, users, token_kind):
    claims = {"sub": str(users["viewer"].id), "role": "viewer"}
    headers = {
        "missing": {},
        "garbage": auth("not.a.token"),
        "expired": auth(jwt.encode({**claims, "exp": datetime.now(UTC) - timedelta(minutes=1)},
                                   settings.jwt_secret, algorithm="HS256")),
        "wrong_secret": auth(jwt.encode({**claims, "exp": datetime.now(UTC) + timedelta(minutes=5)},
                                        "x" * 40, algorithm="HS256")),
    }[token_kind]
    r = anon_api.get("/api/companies", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_open_endpoints_need_no_login(anon_api):
    for path in ("/health", "/ready", "/openapi.json", "/docs"):
        assert anon_api.get(path).status_code == 200, path


def test_viewer_can_read_but_not_change(anon_api, users, db):
    token = login(anon_api, "viewer@test.local", "view-pass-123").json()["access_token"]
    company = make_company(db)
    assert anon_api.get("/api/companies", headers=auth(token)).status_code == 200
    assert anon_api.get("/api/exports", headers=auth(token)).status_code == 200
    for method, path, body in [
        ("post", "/api/companies", {"name": "X", "website": "x.example"}),
        ("post", "/api/runs", {"company_ids": [company.id]}),
        ("post", f"/api/companies/{company.id}/rescan", None),
        ("post", "/api/runs/1/cancel", None),
        ("post", "/api/jobs/1/retry", None),
        ("post", f"/api/companies/{company.id}/overrides",
         {"category": "grain", "new_status": "yes", "reason": "checked", "expected_version": 0}),
    ]:
        r = getattr(anon_api, method)(path, json=body, headers=auth(token))
        assert r.status_code == 403, (path, r.text)
        assert r.json()["error"] == {"code": "FORBIDDEN", "message": "Reviewer role required.", "details": {}}
    r = anon_api.post("/api/uploads", files={"file": ("c.csv", b"company_name,website\nA,a.example\n")},
                      headers=auth(token))
    assert r.status_code == 403


def test_reviewer_can_change(anon_api, users):
    token = login(anon_api, "reviewer@test.local", "rev-pass-123").json()["access_token"]
    r = anon_api.post("/api/companies", json={"name": "New Co-op", "website": "new.example"}, headers=auth(token))
    assert r.status_code == 201


def test_login_is_rate_limited(anon_api, users, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    try:
        codes = [login(anon_api, "viewer@test.local", "wrong").status_code for _ in range(11)]
        right_password = login(anon_api, "viewer@test.local", "view-pass-123")  # still blocked this minute
    finally:
        limiter.reset()
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    assert right_password.status_code == 429
    assert right_password.json()["error"]["code"] == "RATE_LIMITED"
