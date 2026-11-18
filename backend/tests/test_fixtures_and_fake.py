"""The local fixture websites, the test-only hooks (and that production switches them off), the fake AI provider."""
import importlib.util
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from sqlalchemy import select

from app.classifier.pipeline import classify_job
from app.classifier.providers import build_structured_model, provider_order
from app.crawler.crawl import crawl_site
from app.crawler.fetch import fixture_routing_enabled, make_client
from app.crawler.safety import UnsafeURLError, check_url_is_safe
from app.crawler.store import save_pages
from app.db.models import Classification
from tests.factories import make_company, make_run

SERVER_FILE = Path(__file__).resolve().parents[2] / "fixtures" / "server.py"


@pytest.fixture(scope="module")
def fixture_server():
    """The real fixtures/server.py on a free local port, for this test module."""
    spec = importlib.util.spec_from_file_location("fixture_server", SERVER_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def fixtures_on(fixture_server, crawler_settings, no_sleep):
    crawler_settings(environment="development", crawl_fixture_server=fixture_server,
                     crawl_allowed_private_hosts="*.fixture.test")


def test_fixture_site_is_crawled_with_its_own_domain(fixtures_on):
    result = crawl_site("http://clear-coop.fixture.test/")
    urls = [p.url for p in result.pages]
    assert all(p.outcome == "ok" for p in result.pages), [(p.url, p.outcome) for p in result.pages]
    assert urls[0] == "http://clear-coop.fixture.test/"  # the original URL, not 127.0.0.1
    assert "http://clear-coop.fixture.test/grain" in urls
    assert any("cash bids" in (p.text or "") for p in result.pages)


def test_numbered_copies_map_to_the_same_site(fixtures_on):
    result = crawl_site("http://pet-store-042.fixture.test/")
    assert result.pages[0].outcome == "ok" and "Happy Tails" in result.pages[0].text


def test_redirect_to_a_private_ip_is_still_blocked(fixtures_on):
    result = crawl_site("http://redirect-to-private.fixture.test/")
    assert result.pages[0].outcome == "blocked_unsafe"
    assert "10.0.0.5" in result.pages[0].error_detail  # only *.fixture.test is allowlisted, not private IPs


def test_robots_blocked_and_broken_and_empty_sites(fixtures_on):
    assert crawl_site("http://robots-blocked.fixture.test/").pages[0].outcome == "robots_disallowed"
    broken = crawl_site("http://broken-site.fixture.test/").pages[0]
    assert (broken.outcome, broken.http_status) == ("http_error", 500)
    assert crawl_site("http://empty-site.fixture.test/").pages[0].outcome == "empty"


def test_hooks_are_off_in_production(fixture_server, crawler_settings):
    crawler_settings(environment="production", crawl_fixture_server=fixture_server,
                     crawl_allowed_private_hosts="*.fixture.test")
    assert fixture_routing_enabled() is False
    with make_client() as client:
        assert not client._mounts  # no fixture transport
    with pytest.raises(UnsafeURLError):
        check_url_is_safe("http://10.0.0.5/")
    # *.fixture.test is no longer allowlisted, so its address must be resolved and checked like any other
    from app.crawler.safety import is_allowlisted
    assert not is_allowlisted("clear-coop.fixture.test")


def test_fake_provider_is_refused_in_production(crawler_settings):
    crawler_settings(environment="production", ai_provider="fake", ai_fallback_providers="")
    assert provider_order() == []
    with pytest.raises(ValueError, match="disabled in production"):
        build_structured_model("fake")


def test_fake_provider_gives_seven_verified_answers(db, fixtures_on, crawler_settings):
    crawler_settings(ai_provider="fake", ai_fallback_providers="")
    company = make_company(db, 1)
    company.website_url = "http://fuel-delivery-only.fixture.test/"
    _, (job,) = make_run(db, [company])
    save_pages(db, job.id, crawl_site(company.website_url))
    db.commit()

    result = classify_job(db, job.id)

    rows = {c.category: c for c in db.scalars(select(Classification).where(Classification.job_id == job.id))}
    assert len(rows) == 7 and result.provider == "fake"
    assert rows["energy"].status == "yes"
    assert rows["energy"].evidence[0].quote_verified
    assert "propane" in rows["energy"].evidence[0].quote.lower()
    assert rows["energy"].model_name == "fake-keyword-v1"
