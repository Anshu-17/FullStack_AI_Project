from fastapi.testclient import TestClient

from app.db.deps import get_db
from app.db.models import Company
from app.main import app


def test_stats_counts_come_from_the_database(db):
    db.add(Company(name="Prairie Co-op", website_url="https://prairiecoop.example/",
                   canonical_domain="prairiecoop.example"))
    db.flush()
    app.dependency_overrides[get_db] = lambda: db  # use the test transaction
    try:
        body = TestClient(app).get("/api/stats").json()
    finally:
        app.dependency_overrides.clear()
    assert body["companies"] == 1
    assert body["runs"] == 0
    assert set(body["jobs"]) == {"queued", "running", "completed", "review_required", "failed", "cancelled"}
