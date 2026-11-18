from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_reports_database_and_migration():
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["migration"]  # current Alembic revision id


def test_every_response_has_a_request_id():
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")


def test_caller_request_id_is_echoed_back():
    r = client.get("/health", headers={"X-Request-ID": "demo-123"})
    assert r.headers["X-Request-ID"] == "demo-123"
