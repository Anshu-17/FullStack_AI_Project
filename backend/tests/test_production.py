"""Production safety: database URL handling, worker defaults, seed passwords, test-only features off."""
import pytest

from app.config import Settings
from app.db.session import connect_args_for

SECRET = "x" * 48


def prod(**kw) -> Settings:
    return Settings(_env_file=None, environment="production", jwt_secret=SECRET, **kw)


def test_supabase_session_pooler_url_is_accepted_as_shown():
    s = prod(database_url="postgresql://postgres.abcd:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres")
    assert s.database_url.startswith("postgresql+psycopg://postgres.abcd:")
    assert s.database_url.endswith("?sslmode=require")


def test_existing_sslmode_and_local_urls_are_left_alone():
    s = prod(database_url="postgresql+psycopg://u:p@db.abcd.supabase.co:5432/postgres?sslmode=verify-full")
    assert s.database_url.count("sslmode=") == 1 and s.database_url.endswith("verify-full")
    local = prod(database_url="postgres://u:p@localhost:5432/bep")
    assert local.database_url == "postgresql+psycopg://u:p@localhost:5432/bep"  # no ssl added for localhost


def test_prepared_statements_are_off_through_the_pooler():
    assert connect_args_for("postgresql+psycopg://u:p@aws-0-x.pooler.supabase.com:5432/postgres") == {
        "prepare_threshold": None}
    assert connect_args_for("postgresql+psycopg://u:p@host:6543/postgres") == {"prepare_threshold": None}
    assert connect_args_for("postgresql+psycopg://u:p@localhost:5432/bep") == {}


def test_production_runs_one_worker_thread_unless_set():
    assert prod().worker_concurrency == 1
    assert prod(worker_concurrency=3).worker_concurrency == 3  # explicit value wins
    assert Settings(_env_file=None, environment="development").worker_concurrency == 2


def test_production_seed_requires_passwords_and_prints_none(db, monkeypatch, capsys):
    from app.config import settings
    from app.db import seed

    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(seed.SeedError, match="SEED_REVIEWER_PASSWORD"):
        seed.seed_user(db, "new-reviewer@test.local", "reviewer", "")
    assert "generated" not in capsys.readouterr().out  # nothing generated, nothing printed

    seed.seed_user(db, "new-reviewer@test.local", "reviewer", "a-password-from-the-environment")
    out = capsys.readouterr().out
    assert "created" in out and "a-password-from-the-environment" not in out


def test_test_only_features_are_off_in_production(crawler_settings):
    from app.classifier.providers import provider_order
    from app.crawler.fetch import fixture_routing_enabled
    from app.crawler.safety import is_allowlisted

    crawler_settings(environment="production", crawl_fixture_server="127.0.0.1:8765",
                     crawl_allowed_private_hosts="*.fixture.test", ai_provider="fake", ai_fallback_providers="fake")
    assert fixture_routing_enabled() is False
    assert is_allowlisted("clear-coop.fixture.test") is False
    assert provider_order() == []  # the fake provider is never used in production
