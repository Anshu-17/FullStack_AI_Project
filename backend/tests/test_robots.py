"""robots.txt is respected, with RFC 9309 behaviour for missing / failing robots files."""
import respx

from app.crawler.crawl import crawl_site
from app.crawler.fetch import make_client
from app.crawler.robots import robots_allows
from app.db.enums import PageOutcome

SITE = "https://coop.example"


def allows(url):
    with make_client() as client:
        return robots_allows(client, url, {})


@respx.mock
def test_disallowed_path_is_recorded_as_robots_disallowed(fake_dns):
    respx.get(f"{SITE}/robots.txt").respond(200, text="User-agent: *\nDisallow: /private\n")
    respx.get(f"{SITE}/").respond(200, html='<a href="/private/prices">Prices</a> <a href="/about">About</a>')
    private = respx.get(f"{SITE}/private/prices").respond(200, html="<p>secret</p>")
    respx.get(f"{SITE}/about").respond(200, html="<p>About us</p>")

    result = crawl_site(SITE)

    outcomes = {p.url: p.outcome for p in result.pages}
    assert outcomes[f"{SITE}/private/prices"] == PageOutcome.ROBOTS_DISALLOWED
    assert outcomes[f"{SITE}/about"] == PageOutcome.OK
    assert not private.called  # the disallowed page was never requested


@respx.mock
def test_rules_for_our_user_agent_apply(fake_dns):
    respx.get(f"{SITE}/robots.txt").respond(200, text="User-agent: BusinessEvidenceBot\nDisallow: /\n")
    assert not allows(f"{SITE}/about")


@respx.mock
def test_robots_404_allows_everything(fake_dns):
    respx.get(f"{SITE}/robots.txt").respond(404)
    assert allows(f"{SITE}/anything")


@respx.mock
def test_robots_500_disallows_everything(fake_dns, no_sleep):
    respx.get(f"{SITE}/robots.txt").respond(500)
    assert not allows(f"{SITE}/about")


@respx.mock
def test_robots_unreachable_disallows_everything(fake_dns):
    fake_dns["coop.example"] = None  # DNS failure
    assert not allows(f"{SITE}/about")


@respx.mock
def test_robots_is_fetched_once_per_site(fake_dns):
    route = respx.get(f"{SITE}/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
    cache = {}
    with make_client() as client:
        for path in ("/a", "/b", "/c"):
            assert robots_allows(client, f"{SITE}{path}", cache)
    assert route.call_count == 1
