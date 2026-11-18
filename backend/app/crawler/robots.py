"""robots.txt: respect what the website owner allows (RFC 9309 behaviour).

How the robots.txt fetch result is interpreted (RFC 9309, section 2.3.1):
- 200          -> parse the rules
- 4xx (404...) -> "unavailable": no rules, everything allowed
- 5xx, timeout, network error -> "unreachable": assume EVERYTHING is disallowed
- 429 (too many requests) is treated like 5xx: the server is asking us to back off

Simplifications (documented in the decision log):
- Python's urllib.robotparser does not support '*' / '$' wildcards in paths and
  uses first-match instead of longest-match. Fine for typical company sites.
- A robots.txt bigger than the size limit is treated as unreachable (disallow).
"""
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings
from app.crawler.fetch import fetch_page
from app.db.enums import PageOutcome

ROBOTS_MAX_BYTES = 500_000  # RFC 9309 asks crawlers to read at least 500 KiB


def _origin(url: str) -> str:
    """'https://example.com:8443/a/b' -> 'https://example.com:8443' (robots.txt is per origin)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def load_robots(client: httpx.Client, origin: str) -> RobotFileParser:
    """Fetch and parse <origin>/robots.txt using the same safe fetch as pages."""
    parser = RobotFileParser()
    result = fetch_page(client, f"{origin}/robots.txt", max_bytes=ROBOTS_MAX_BYTES, html_only=False)
    status = result.http_status or 0

    if result.outcome == PageOutcome.OK:
        parser.parse(result.html.splitlines())
    elif result.outcome == PageOutcome.EMPTY:
        parser.parse([])  # an empty robots.txt has no rules -> everything allowed
    elif result.outcome == PageOutcome.HTTP_ERROR and 400 <= status < 500 and status != 429:
        parser.allow_all = True  # "unavailable" (e.g. 404): no restrictions
    else:
        parser.disallow_all = True  # 5xx / 429 / timeout / unreachable / unsafe / too large
    return parser


def robots_allows(client: httpx.Client, url: str, cache: dict[str, RobotFileParser]) -> bool:
    """May our user agent fetch `url`? `cache` keeps one parsed robots.txt per origin for this crawl."""
    origin = _origin(url)
    if origin not in cache:
        cache[origin] = load_robots(client, origin)
    return cache[origin].can_fetch(settings.crawl_user_agent, url)
