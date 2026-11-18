"""Crawl ONE company website and return the pages. Never classifies anything.

Candidates: links found on fetched pages, plus the URLs listed in the site's sitemap
(app/crawler/sitemap.py, read once after the homepage).

Which candidate is fetched next (deterministic):
1. Category balance first: for each category group (agronomy, grain, energy, feed, gas station,
   retail store, locations) that has no fetched page yet, take the best candidate whose URL path or
   link text has that group's words. So one big section (e.g. 20 agronomy pages) can no longer use
   up the whole budget while the store / fuel / feed pages are never fetched.
2. Then the rest of the budget by score (sum of the matched word weights) minus 3 for every page
   already fetched from the same folder, so '/cash-bids/<date>' x 20 can't fill it, while a strong
   page still beats a weak page from an untouched folder.
"blog / news / careers / privacy" candidates always come last. Ties: the first discovered wins.

Stops at whichever limit is hit first: page count, total bytes (sitemaps included), deadline.
(The depth limit just stops following links deeper than crawl_max_depth.)

Politeness: one request at a time to a site (well under crawl_per_host_concurrency).
Running several companies in parallel is the worker's job, not the crawler's.
"""
import hashlib
import itertools
import re
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.crawler.extract import extract
from app.crawler.fetch import FetchResult, fetch_page, make_client
from app.crawler.robots import robots_allows
from app.crawler.sitemap import discover_sitemap_urls
from app.crawler.urls import (
    canonical_domain,
    is_probably_page,
    normalize_page_url,
    path_prefix,
    same_site,
    under_path,
)
from app.db.enums import PageOutcome
from app.log_config import get_logger

log = get_logger("crawler")

# Words in a link's URL PATH or LINK TEXT that hint at evidence for a category group, with a weight
# (3 = strong hint, 1 = weak). Matched as whole words, plural "s" / "es" allowed, "-" "_" "/" = space:
# "ace" matches /ace-hardware but not /marketplace; "c store" matches /c-store.
GROUP_WORDS: dict[str, dict[str, int]] = {
    "agronomy": {"agronomy": 3, "agronomic": 3, "seed": 2, "fertilizer": 2, "crop": 2, "chemical": 1,
                 "precision": 1, "soil": 1, "application": 1},
    "grain": {"grain": 3, "elevator": 2, "bid": 2, "cash bid": 3, "commodity": 1, "storage": 1},
    "energy": {"energy": 3, "propane": 3, "diesel": 2, "fuel": 2, "petroleum": 2, "lubricant": 2, "oil": 1},
    "feed": {"feed": 3, "nutrition": 2, "livestock": 2, "mill": 2, "dairy": 1, "animal": 1},
    "gas_station": {"cardlock": 3, "c store": 3, "convenience": 3, "station": 2, "cenex": 2, "gas": 2,
                    "pump": 2, "fuel": 1},
    "retail_store": {"store": 3, "farm store": 3, "hardware": 3, "shop": 2, "ace": 2, "lumber": 2, "retail": 2,
                     "c store": 1, "convenience": 1},
    "locations": {"location": 3, "find us": 3, "contact": 2, "direction": 1, "hour": 1},
}
GROUP_ORDER = tuple(GROUP_WORDS)  # fixed order for the balanced phase (deterministic)
GENERAL_WORDS = {"product": 1, "service": 1, "about": 1}  # no group, but more useful than an average page
LOW_PRIORITY_WORDS = ("blog", "news", "career", "job", "login", "privacy", "cookie")
FOLDER_PENALTY = 3  # score phase: -3 per page already fetched from the same folder (spreads over sections)


@dataclass(frozen=True)
class LinkHint:
    """What a link's URL path + text suggest about the page behind it."""

    low: bool                 # blog / news / careers ...: fetched last
    weights: dict[str, int]   # group -> sum of its matched word weights ("grain commodities" = 3 + 1)
    score: int                # total of all matched weights (groups + general words)


def _words(url: str, link_text: str) -> str:
    """URL path + link text, lower-case, every non-letter/digit -> space, padded: ' ace hardware '."""
    path = url.split("://", 1)[-1].partition("/")[2]  # ignore the hostname ("graincoop.com" is not a hint)
    return " " + re.sub(r"[^a-z0-9]+", " ", f"{path} {link_text}".lower()).strip() + " "


def _has(haystack: str, word: str) -> bool:
    return any(f" {word}{ending} " in haystack for ending in ("", "s", "es"))


def link_hints(url: str, link_text: str) -> LinkHint:
    haystack = _words(url, link_text)
    low = any(_has(haystack, w) for w in LOW_PRIORITY_WORDS)  # "/careers/agronomy-sales" is a job ad
    weights = {}
    for group, words in GROUP_WORDS.items():
        found = [weight for word, weight in words.items() if _has(haystack, word)]
        if found:
            weights[group] = sum(found)
    score = sum(weights.values()) + sum(w for word, w in GENERAL_WORDS.items() if _has(haystack, word))
    return LinkHint(low=low, weights={} if low else weights, score=0 if low else score)


@dataclass
class Candidate:
    url: str
    depth: int
    order: int      # discovery order: the tie-breaker
    hint: LinkHint
    source: str     # "start" | "link" | "sitemap"


def parent_folder(url: str) -> str:
    """'https://x.com/grain/cash-bids/2024-05' -> 'x.com/grain/cash-bids'."""
    return url.split("://", 1)[-1].rsplit("/", 1)[0]


def choose_next(candidates: list[Candidate], covered: set[str],
                folders: dict[str, int] | None = None) -> tuple[Candidate, str, str | None]:
    """Pick the next page to fetch: (candidate, why, the group it was chosen for or None).
    `covered` = groups that already have a successfully fetched page;
    `folders` = pages fetched so far per parent folder (score phase: spread over sections, so twenty
    '/cash-bids/<date>' pages can't fill the budget)."""
    folders = folders or {}
    for group in GROUP_ORDER:  # 1. category balance
        if group in covered:
            continue
        options = [c for c in candidates if group in c.hint.weights]
        if options:
            # strongest hint for this group, then the most SPECIFIC page (fewest hints for other groups):
            # "/feed-grain/grain-commodities" beats "/feed-grain/feed-products" for grain
            best = min(options, key=lambda c: (-c.hint.weights[group], c.hint.score - c.hint.weights[group],
                                               c.depth, c.order))
            return best, f"first page for {group}", group
    def adjusted(c: Candidate) -> int:  # score minus FOLDER_PENALTY per page already fetched from its folder
        return c.hint.score - FOLDER_PENALTY * folders.get(parent_folder(c.url), 0)

    best = min(candidates, key=lambda c: (c.hint.low, -adjusted(c), c.depth, c.order))  # 2. by score
    return best, "low priority" if best.hint.low else f"score {adjusted(best)}", None


@dataclass
class CrawledPage(FetchResult):
    """A fetch result plus what the crawler learned about it."""

    depth: int = 0
    title: str | None = None
    text: str | None = None
    reason: str | None = None  # why the crawler chose this page (shown by the CLIs and in the logs)


@dataclass
class CrawlResult:
    start_url: str
    pages: list[CrawledPage] = field(default_factory=list)
    stopped_reason: str = "completed"  # completed | page_limit | byte_limit | deadline | invalid_start_url
    total_bytes: int = 0
    elapsed_ms: int = 0
    # Set when the homepage redirected to ANOTHER domain, e.g. "https://fscooperatives.com/insightfs".
    # Only pages under that address are crawled (a shared site may host other companies too).
    redirected_to: str | None = None
    duplicate_pages: int = 0  # pages whose text equals an earlier page's: kept, but not counted in the budget
    sitemap_files: list[str] = field(default_factory=list)  # sitemap files read
    sitemap_candidates: int = 0  # new candidate pages the sitemap added


DUPLICATE_PREFIX = "duplicate_of:"  # error_detail of a page whose text is identical to an earlier page


def is_duplicate(page) -> bool:
    """A page (CrawledPage or Page row) marked as having the same text as an earlier page of the crawl."""
    return (page.error_detail or "").startswith(DUPLICATE_PREFIX)


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
    prefix = "/"  # only follow links under this path; narrowed after a cross-domain homepage redirect
    robots_cache: dict = {}
    order = itertools.count()  # tie-breaker: first discovered first
    candidates = [Candidate(start, 0, next(order), link_hints(start, ""), "start")]
    seen = {start}  # every URL ever queued: guarantees no page is fetched twice
    covered: set[str] = set()  # category groups that already have a successfully fetched page
    folders: dict[str, int] = {}  # pages fetched per parent folder (spreads the score phase over sections)
    text_hashes: dict[str, str] = {}  # sha256 of page text -> first URL with that text
    sitemap_done = False

    def add_candidate(link_url: str, link_text: str, depth: int, source: str) -> None:
        link = normalize_page_url(link_url)
        if (not link or link in seen or not same_site(link, domain)
                or not under_path(link, prefix) or not is_probably_page(link)):
            return
        seen.add(link)
        candidates.append(Candidate(link, depth, next(order), link_hints(link, link_text), source))

    def budget_left() -> bool:
        return time.perf_counter() < deadline and result.total_bytes < settings.crawl_max_total_bytes

    try:
        while candidates:
            # Duplicate-text pages don't use up the page budget (they add no new evidence).
            if len(result.pages) - result.duplicate_pages >= settings.crawl_max_pages:
                result.stopped_reason = "page_limit"
                break
            if result.total_bytes >= settings.crawl_max_total_bytes:
                result.stopped_reason = "byte_limit"
                break
            if time.perf_counter() >= deadline:
                result.stopped_reason = "deadline"
                break

            chosen, why, for_group = choose_next(candidates, covered, folders)
            candidates.remove(chosen)
            folders[parent_folder(chosen.url)] = folders.get(parent_folder(chosen.url), 0) + 1
            url, depth = chosen.url, chosen.depth
            reason = {"start": "homepage", "sitemap": f"{why} (from sitemap)"}.get(chosen.source, why)

            if not robots_allows(client, url, robots_cache):
                page = CrawledPage(url=url, outcome=PageOutcome.ROBOTS_DISALLOWED, depth=depth,
                                   error_detail="disallowed by robots.txt", reason=reason)
            else:
                page = CrawledPage(**vars(fetch_page(client, url)), depth=depth, reason=reason)

            result.pages.append(page)
            result.total_bytes += page.byte_size or 0
            log.info("crawl.page", url=url, depth=depth, outcome=str(page.outcome),
                     status=page.http_status, bytes=page.byte_size, ms=page.elapsed_ms, reason=reason)

            if page.outcome != PageOutcome.OK:
                continue  # recorded; move on to the next page (its groups stay uncovered)
            # Each fetched page covers ONE group: the group it was chosen for, else its strongest uncovered
            # group with a real hint (>= 2). So a "/c-store" page fetched for gas station does not use up
            # the retail store slot: a hardware store page still gets one.
            uncovered = {g: w for g, w in chosen.hint.weights.items() if g not in covered and w >= 2}
            if for_group or uncovered:
                covered.add(for_group or min(uncovered, key=lambda g: (-uncovered[g], GROUP_ORDER.index(g))))

            page_url = page.final_url or url
            final = normalize_page_url(page_url)
            if final:
                seen.add(final)  # /about redirected to /about-us: don't fetch /about-us again
            new_domain = canonical_domain(page_url)
            if depth == 0 and new_domain and new_domain != domain:
                # The homepage redirected to ANOTHER domain. That may be a shared site hosting several
                # companies (insightfs.com -> fscooperatives.com/insightfs), so we stay under the
                # redirect target's path: /insightfs/... yes, /othercoop/... no.
                domain = new_domain
                prefix = path_prefix(page_url)
                result.redirected_to = page_url
                log.info("crawl.cross_domain_redirect", start_url=start_url, redirected_to=page_url,
                         domain=domain, path_prefix=prefix)

            page.title, page.text, links = extract(page.html, page_url)
            page.html = None  # keep only the cleaned text (raw HTML is not stored)

            # Same text as a page we already have (e.g. "/" and "/home")? Keep the row for the record,
            # but mark it, don't count it, don't send it to the AI, and don't follow its (identical) links.
            digest = hashlib.sha256(page.text.encode("utf-8")).hexdigest() if page.text else None
            if digest and digest in text_hashes:
                page.error_detail = f"{DUPLICATE_PREFIX}{text_hashes[digest]}"
                result.duplicate_pages += 1
                log.info("crawl.duplicate_text", url=url, duplicate_of=text_hashes[digest])
                continue
            if digest:
                text_hashes[digest] = url

            if depth < settings.crawl_max_depth:  # deep enough? then don't queue this page's links
                for link_url, link_text in links:
                    add_candidate(link_url, link_text, depth + 1, "link")

            if depth == 0 and not sitemap_done:  # once, after the homepage (whose redirects set domain/prefix)
                sitemap_done = True
                sitemap = discover_sitemap_urls(client, page_url, domain, robots_cache, budget_left)
                result.total_bytes += sitemap.bytes
                result.sitemap_files = sitemap.files
                before = len(candidates)
                for sitemap_url in sitemap.urls:
                    add_candidate(sitemap_url, "", 1, "sitemap")  # listed by the site itself: like a homepage link
                result.sitemap_candidates = len(candidates) - before
                log.info("crawl.sitemap", files=sitemap.files, urls=len(sitemap.urls),
                         new_candidates=result.sitemap_candidates, bytes=sitemap.bytes)
    finally:
        if own_client:
            client.close()

    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info("crawl.finished", start_url=start_url, pages=len(result.pages),
             stopped_reason=result.stopped_reason, total_bytes=result.total_bytes, ms=result.elapsed_ms)
    return result
