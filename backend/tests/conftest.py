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
