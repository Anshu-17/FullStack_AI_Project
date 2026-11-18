"""Sitemap discovery: parsing, robots 'Sitemap:' lines, one nested level, limits, safety."""
import respx

from app.crawler.crawl import crawl_site
from app.crawler.sitemap import MAX_SITEMAP_URLS, SITEMAP_MAX_BYTES, parse_sitemap

SITE = "https://coop.example"


def urlset(*paths: str) -> str:
    locs = "".join(f"<url><loc>{p if '://' in p else SITE + p}</loc></url>" for p in paths)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'


def index(*urls: str) -> str:
    return "<sitemapindex>" + "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in urls) + "</sitemapindex>"


def xml(body: str):
    return {"headers": {"content-type": "application/xml"}, "text": body}


def home(html: str = "<p>Welcome</p>", robots: str | None = None):
    if robots is None:
        respx.get(f"{SITE}/robots.txt").respond(404)
    else:
        respx.get(f"{SITE}/robots.txt").respond(200, text=robots, headers={"content-type": "text/plain"})
    respx.get(f"{SITE}/").respond(200, html=html)


def page(path: str):
    return respx.get(f"{SITE}{path}").respond(200, html=f"<p>{path} page</p>")


# ------------------------------------------------------------------ parsing

def test_parse_urlset_and_index():
    assert parse_sitemap(urlset("/a", "/b")) == (False, [f"{SITE}/a", f"{SITE}/b"])
    assert parse_sitemap(index(f"{SITE}/page-sitemap.xml")) == (True, [f"{SITE}/page-sitemap.xml"])


def test_parse_is_forgiving_and_never_expands_entities():
    truncated = urlset("/a", "/b")[:-30]  # cut off mid-document: still yields what is there
    assert parse_sitemap(truncated)[1] == [f"{SITE}/a"]
    assert parse_sitemap("<urlset><loc> https://coop.example/x?a=1&amp;b=2 </loc></urlset>")[1] == [
        "https://coop.example/x?a=1&b=2"]
    bomb = '<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]><urlset><loc>&b;</loc></urlset>'
    assert parse_sitemap(bomb)[1] == ["&b;"]  # no XML parser: entities are never expanded
    assert parse_sitemap("not xml at all") == (False, [])
    many = urlset(*(f"/p{i}" for i in range(MAX_SITEMAP_URLS + 50)))
    assert len(parse_sitemap(many)[1]) == MAX_SITEMAP_URLS


# ------------------------------------------------------------------ discovery during a crawl

@respx.mock
def test_sitemap_xml_pages_become_candidates(fake_dns):
    home()  # the homepage links to nothing
    respx.get(f"{SITE}/sitemap.xml").respond(200, **xml(urlset("/", "/stores", "/blog/post-1")))
    stores, blog = page("/stores"), page("/blog/post-1")
    result = crawl_site(SITE)
    assert result.sitemap_files == [f"{SITE}/sitemap.xml"]
    assert result.sitemap_candidates == 2  # "/" was already seen
    assert stores.called and blog.called
    reasons = {p.url: p.reason for p in result.pages}
    assert reasons[f"{SITE}/stores"] == "first page for retail_store (from sitemap)"
    assert [p.url for p in result.pages][-1] == f"{SITE}/blog/post-1"  # low priority last


@respx.mock
def test_robots_sitemap_lines_and_one_nested_level(fake_dns):
    home(robots=f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap_index.xml\n")
    default = respx.get(f"{SITE}/sitemap.xml").respond(200, **xml(urlset("/never")))
    respx.get(f"{SITE}/sitemap_index.xml").respond(200, **xml(index(
        f"{SITE}/post-sitemap.xml", f"{SITE}/page-sitemap.xml")))
    respx.get(f"{SITE}/page-sitemap.xml").respond(200, **xml(index(f"{SITE}/deeper.xml")))  # index in index
    deeper = respx.get(f"{SITE}/deeper.xml").respond(200, **xml(urlset("/too-deep")))
    respx.get(f"{SITE}/post-sitemap.xml").respond(200, **xml(urlset("/feed-mill")))
    feed = page("/feed-mill")

    result = crawl_site(SITE)
    # page-sitemap first (more useful name), post-sitemap second; the nested index is NOT followed
    assert result.sitemap_files == [f"{SITE}/sitemap_index.xml", f"{SITE}/page-sitemap.xml",
                                    f"{SITE}/post-sitemap.xml"]
    assert not deeper.called and not default.called  # robots named a sitemap: /sitemap.xml not guessed
    assert feed.called


@respx.mock
def test_off_site_sitemaps_and_urls_are_ignored(fake_dns):
    home(robots="User-agent: *\nAllow: /\nSitemap: https://evil.example/sitemap.xml\n")
    evil = respx.get("https://evil.example/sitemap.xml").respond(200, **xml(urlset("/x")))
    respx.get(f"{SITE}/sitemap.xml").respond(200, **xml(urlset("https://other.example/grain", "/grain")))
    other = respx.get("https://other.example/grain").respond(200, html="<p>no</p>")
    grain = page("/grain")
    result = crawl_site(SITE)
    assert not evil.called       # sitemap on another site: not fetched (falls back to /sitemap.xml)
    assert not other.called      # a listed URL on another site: not crawled
    assert grain.called
    assert result.sitemap_candidates == 1


@respx.mock
def test_huge_or_broken_sitemap_is_ignored(fake_dns):
    home()
    huge = urlset("/a") + " " * (SITEMAP_MAX_BYTES + 10)
    respx.get(f"{SITE}/sitemap.xml").respond(200, **xml(huge))
    result = crawl_site(SITE)
    assert result.sitemap_files == [] and result.sitemap_candidates == 0
    assert [p.url for p in result.pages] == [f"{SITE}/"]


@respx.mock
def test_sitemap_redirect_to_private_ip_is_blocked(fake_dns):
    fake_dns["internal.example"] = ["10.0.0.5"]
    home()
    respx.get(f"{SITE}/sitemap.xml").respond(302, headers={"Location": "http://internal.example/sitemap.xml"})
    internal = respx.get("http://internal.example/sitemap.xml").respond(200, **xml(urlset("/a")))
    result = crawl_site(SITE)
    assert not internal.called  # SSRF check on the redirect hop
    assert result.sitemap_files == []


@respx.mock
def test_sitemap_respects_robots_disallow(fake_dns):
    home(robots="User-agent: *\nDisallow: /sitemap.xml\n")
    sitemap = respx.get(f"{SITE}/sitemap.xml").respond(200, **xml(urlset("/a")))
    crawl_site(SITE)
    assert not sitemap.called


@respx.mock
def test_sitemap_bytes_count_toward_the_byte_budget(fake_dns, crawler_settings):
    crawler_settings(crawl_max_total_bytes=2_000)
    home()
    body = urlset("/a", "/b") + " " * 3_000  # under the sitemap cap, over the site's byte budget
    respx.get(f"{SITE}/sitemap.xml").respond(200, **xml(body))
    a = page("/a")
    result = crawl_site(SITE)
    assert result.total_bytes > 2_000
    assert result.stopped_reason == "byte_limit"
    assert not a.called
