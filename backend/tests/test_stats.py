from app.db.models import Company


def test_stats_counts_come_from_the_database(api, db):
    db.add(Company(name="Prairie Co-op", website_url="https://prairiecoop.example/",
                   canonical_domain="prairiecoop.example"))
    db.flush()
    body = api.get("/api/stats").json()
    assert body["companies"] == 1
    assert body["runs"] == 0
    assert set(body["jobs"]) == {"queued", "running", "completed", "review_required", "failed", "cancelled"}
