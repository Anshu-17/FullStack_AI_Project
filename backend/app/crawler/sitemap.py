"""Sitemap discovery: extra candidate pages from the website's own sitemap (sitemaps.org format).

Why: a homepage often links only to a few sections; the pages that prove a business line (a store,
a fuel station, a feed mill) can be one level deeper. The sitemap lists them.

Where we look: the "Sitemap:" lines of robots.txt; if there are none, <origin>/sitemap.xml.

Safety (same rules as pages):
- fetched with the same safe fetch: SSRF check on the URL and on every redirect hop, timeouts,
  size cap (SITEMAP_MAX_BYTES), no scripts
- the sitemap file must be on the company's own site and allowed by robots.txt
- at most MAX_SITEMAP_FILES files and MAX_SITEMAP_URLS URLs per crawl
- a sitemap INDEX is followed one level only (an index inside an index is ignored)
- the URLs found are only candidates: the crawler still filters them (same site, same path prefix,
  no files) and checks robots.txt before fetching any of them

Parsing: a simple regex for <loc>...</loc>, no XML parser. So there are no XML entity attacks
("billion laughs"), and a broken or truncated sitemap still yields the URLs it does contain.
Compressed sitemaps (.xml.gz) are skipped.
"""
import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.crawler.fetch import fetch_page
from app.crawler.robots import robots_allows
from app.crawler.urls import normalize_page_url, same_site
from app.db.enums import PageOutcome

SITEMAP_MAX_BYTES = 500_000  # per file; typical company sitemaps are 2-50 KB
MAX_SITEMAP_FILES = 3        # e.g. one index + two of its child sitemaps
MAX_SITEMAP_URLS = 1000      # page URLs kept in total

LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
# Child sitemaps of an index, most useful first (WordPress / Yoast names like page-sitemap.xml)
USEFUL_CHILD_WORDS = ("page", "location", "store", "product", "service")
LESS_USEFUL_CHILD_WORDS = ("post", "blog", "news", "event", "tag", "author", "category")


@dataclass
class SitemapResult:
    urls: list[str] = field(default_factory=list)   # page URLs listed (candidates, not yet filtered)
    files: list[str] = field(default_factory=list)  # sitemap files read successfully
    bytes: int = 0                                  # bytes downloaded (counts toward the crawl's byte budget)


def parse_sitemap(text: str) -> tuple[bool, list[str]]:
    """(is_index, urls). A <sitemapindex> lists other sitemaps; a <urlset> lists pages."""
    is_index = "<sitemapindex" in text.lower()
    urls = [html.unescape(loc).strip() for loc in LOC_RE.findall(text)]
    return is_index, [u for u in urls if u][:MAX_SITEMAP_URLS]


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _usable(url: str, domain: str) -> bool:
    """A sitemap file we are willing to fetch: http(s), on the company's own site, not compressed."""
    normalized = normalize_page_url(url)
    return bool(normalized) and same_site(normalized, domain) and not urlsplit(normalized).path.endswith(".gz")


def _child_rank(url: str) -> int:
    lower = url.lower()
    if any(w in lower for w in USEFUL_CHILD_WORDS):
        return 0
    return 2 if any(w in lower for w in LESS_USEFUL_CHILD_WORDS) else 1


def discover_sitemap_urls(client: httpx.Client, page_url: str, domain: str, robots_cache: dict,
                          budget_left: Callable[[], bool]) -> SitemapResult:
    """Read the site's sitemap(s) and return the page URLs they list. Never raises.

    page_url = the homepage URL after redirects (its origin is where robots.txt / sitemap.xml live).
    budget_left() = False once the crawl's deadline or byte budget is used up.
    """
    result = SitemapResult()
    origin = _origin(page_url)
    robots_allows(client, f"{origin}/", robots_cache)  # makes sure robots.txt of this origin is loaded
    declared = robots_cache[origin].site_maps() or []  # the "Sitemap:" lines (None if there are none)
    todo = [(url, 0) for url in declared if _usable(url, domain)] or [(f"{origin}/sitemap.xml", 0)]

    while todo and len(result.files) < MAX_SITEMAP_FILES and len(result.urls) < MAX_SITEMAP_URLS:
        if not budget_left():
            break
        url, level = todo.pop(0)
        if not robots_allows(client, url, robots_cache):
            continue
        fetched = fetch_page(client, url, max_bytes=SITEMAP_MAX_BYTES, html_only=False)
        result.bytes += fetched.byte_size or 0
        if fetched.outcome != PageOutcome.OK:
            continue  # 404 / too large / blocked / timeout: no sitemap from this file
        result.files.append(url)
        is_index, locs = parse_sitemap(fetched.html)
        if is_index:
            if level == 0:  # one nested level only
                children = sorted((u for u in locs if _usable(u, domain)), key=_child_rank)  # stable: deterministic
                todo += [(u, 1) for u in children]
            continue
        room = MAX_SITEMAP_URLS - len(result.urls)
        result.urls += locs[:room]
    return result
