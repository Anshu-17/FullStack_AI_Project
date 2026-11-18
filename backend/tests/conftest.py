"""Test setup: a separate test database, migrated with Alembic (so migrations are tested too).

Set TEST_DATABASE_URL to point somewhere else; default is a local `bep_test` database.
Each test runs inside a transaction that is rolled back, so tests don't affect each other.
"""
import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:devpass@localhost:5432/bep_test"
)
os.environ.setdefault("LOG_JSON", "false")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import engine  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    command.downgrade(cfg, "base")  # start clean
    command.upgrade(cfg, "head")
    yield


PUBLIC_TEST_IP = "93.184.216.34"  # a public address; nothing is ever really contacted


@pytest.fixture()
def fake_dns(monkeypatch):
    """Replace real DNS. Unknown names resolve to a public IP; tests add records to the returned dict.

    records["host"] = ["10.0.0.5"]  -> host resolves to that address
    records["host"] = None          -> DNS failure for host
    """
    from app.crawler import safety

    records: dict[str, list[str] | None] = {}

    def resolve(host):
        if host not in records:
            return [PUBLIC_TEST_IP]
        if records[host] is None:
            raise safety.DNSResolutionError(f"could not resolve {host}")
        return records[host]

    monkeypatch.setattr(safety, "resolve_host", resolve)
    return records


@pytest.fixture()
def no_sleep(monkeypatch):
    """Retries don't really wait in tests. Returns the list of requested waits (seconds)."""
    from app.crawler import fetch

    waits: list[float] = []
    monkeypatch.setattr(fetch, "sleep", waits.append)
    return waits


@pytest.fixture()
def crawler_settings(monkeypatch):
    """Lets a test change a crawl setting just for itself: crawler_settings(crawl_max_pages=3)."""
    from app.config import settings

    def change(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)

    return change


APP_TABLES = ("ai_usage, evidence, classifications, overrides, pages, job_events, attempts, jobs, runs, "
              "upload_rows, uploads, companies, policy_versions, users")


@pytest.fixture()
def fresh_db():
    """For tests that need REAL commits on several connections (worker threads, concurrent claims).

    The normal `db` fixture rolls everything back, but other connections can't see uncommitted data.
    So these tests commit for real into bep_test, and the tables are emptied before and after.
    Never combine with the `db` fixture in one test.
    """
    from sqlalchemy import text

    from app.db.models import PolicyVersion
    from app.db.session import SessionLocal

    def wipe():
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {APP_TABLES} RESTART IDENTITY CASCADE"))

    wipe()
    with SessionLocal() as s:
        s.add(PolicyVersion(version="v1", description="test policy", rules={}, is_active=True))
        s.commit()
    yield SessionLocal
    wipe()


@pytest.fixture()
def api(db):
    """HTTP client for the API, using the test's rolled-back session."""
    from fastapi.testclient import TestClient

    from app.db.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def db():
    """A session whose changes are rolled back after the test."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()
