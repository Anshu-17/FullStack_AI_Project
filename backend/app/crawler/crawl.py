"""Crawl ONE company website and return the pages. Never classifies anything.

Order of work: a priority queue. Pages whose URL or link text mentions our
business lines (grain, agronomy, propane, ...) go first, "blog/news/careers"
pages go last, everything else in between. Within the same priority it is
breadth-first (shallower pages first). Why: we only fetch a few pages per site,
so they should be the pages most likely to contain evidence.

Stops at whichever limit is hit first: page count, total bytes, deadline.
(The depth limit just stops following links deeper than crawl_max_depth.)

Politeness: one request at a time to a site (well under crawl_per_host_concurrency).
Running several companies in parallel is the worker's job, not the crawler's.
"""
import heapq
import itertools
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.crawler.extract import extract
from app.crawler.fetch import FetchResult, fetch_page, make_client
from app.crawler.robots import robots_allows
from app.crawler.urls import canonical_domain, is_probably_page, normalize_page_url, same_site
from app.db.enums import PageOutcome
from app.log_config import get_logger

log = get_logger("crawler")

HIGH_PRIORITY_WORDS = (
    "product", "service", "location", "store", "grain", "agronomy", "agronomic", "seed",
    "fertilizer", "crop", "feed", "nutrition", "energy", "propane", "fuel", "diesel", "cardlock", "about",
)
LOW_PRIORITY_WORDS = ("blog", "news", "career", "job", "login", "privacy", "cookie")


@dataclass
class CrawledPage(FetchResult):
    """A fetch result plus what the crawler learned about it."""

    depth: int = 0
    title: str | None = None
    text: str | None = None


@dataclass
class CrawlResult:
    start_url: str
    pages: list[CrawledPage] = field(default_factory=list)
    stopped_reason: str = "completed"  # completed | page_limit | byte_limit | deadline | invalid_start_url
    total_bytes: int = 0
    elapsed_ms: int = 0


def link_priority(url: str, link_text: str) -> int:
    """0 = likely evidence, 1 = normal, 2 = unlikely to help. Lower is fetched first."""
    path = url.split("://", 1)[-1].partition("/")[2]  # ignore the hostname ("graincoop.com" is not a hint)
    haystack = f"{path} {link_text}".lower()
    if any(word in haystack for word in LOW_PRIORITY_WORDS):
        return 2  # checked first: "/careers/agronomy-sales" is a job ad, not evidence
    if any(word in haystack for word in HIGH_PRIORITY_WORDS):
        return 0
    return 1


def crawl_site(start_url: str, client: httpx.Client | None = None) -> CrawlResult:
    """Crawl one website starting at its homepage. One bad page never stops the crawl."""
    started = time.perf_counter()
    deadline = started + settings.crawl_job_deadline_seconds
    result = CrawlResult(start_url=start_url)

    start = normalize_page_url(start_url)
    domain = canonical_domain(start_url)
    if not start or not domain:
        result.pages.append(CrawledPage(url=start_url, outcome=PageOutcome.ERROR, error_detail="invalid start URL"))
        result.stopped_reason = "invalid_start_url"
        return result

    own_client = client is None
    client = client or make_client()
    robots_cache: dict = {}
    order = itertools.count()  # tie-breaker: same priority and depth -> first discovered first
    queue = [(0, 0, next(order), start)]  # (priority, depth, order, url)
    seen = {start}  # every URL ever queued: guarantees no page is fetched twice

    try:
        while queue:
            if len(result.pages) >= settings.crawl_max_pages:
                result.stopped_reason = "page_limit"
                break
            if result.total_bytes >= settings.crawl_max_total_bytes:
                result.stopped_reason = "byte_limit"
                break
            if time.perf_counter() >= deadline:
                result.stopped_reason = "deadline"
                break

            _priority, depth, _order, url = heapq.heappop(queue)

            if not robots_allows(client, url, robots_cache):
                page = CrawledPage(url=url, outcome=PageOutcome.ROBOTS_DISALLOWED, depth=depth,
                                   error_detail="disallowed by robots.txt")
            else:
                page = CrawledPage(**vars(fetch_page(client, url)), depth=depth)

            result.pages.append(page)
            result.total_bytes += page.byte_size or 0
            log.info("crawl.page", url=url, depth=depth, outcome=str(page.outcome),
                     status=page.http_status, bytes=page.byte_size, ms=page.elapsed_ms)

            if page.outcome != PageOutcome.OK:
                continue  # recorded; move on to the next page

            page_url = page.final_url or url
            final = normalize_page_url(page_url)
            if final:
                seen.add(final)  # /about redirected to /about-us: don't fetch /about-us again
            if depth == 0:
                # Homepage redirected to another domain (e.g. old name -> new name): follow that site.
                domain = canonical_domain(page_url) or domain

            page.title, page.text, links = extract(page.html, page_url)
            page.html = None  # keep only the cleaned text (raw HTML is not stored)

            if depth >= settings.crawl_max_depth:
                continue  # deep enough: don't queue this page's links
            for link_url, link_text in links:
                link = normalize_page_url(link_url)
                if not link or link in seen or not same_site(link, domain) or not is_probably_page(link):
                    continue
                seen.add(link)
                heapq.heappush(queue, (link_priority(link, link_text), depth + 1, next(order), link))
    finally:
        if own_client:
            client.close()

    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info("crawl.finished", start_url=start_url, pages=len(result.pages),
             stopped_reason=result.stopped_reason, total_bytes=result.total_bytes, ms=result.elapsed_ms)
    return result
