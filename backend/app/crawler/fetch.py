"""Fetch ONE page safely. Never raises: every problem becomes a PageOutcome.

Safety rules applied to every request:
- SSRF check on the first URL AND on every redirect hop (redirects followed by hand)
- body streamed and cut off at a size limit (a huge page cannot fill our memory)
- only HTML is accepted for pages
- timeouts on every network operation
- retries only for temporary problems (429, 5xx, timeouts), with backoff + jitter
- we only download text; JavaScript is never executed
"""
import random
import time
from dataclasses import dataclass
from time import sleep  # imported by name so tests can replace it and skip real waiting
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.crawler.safety import DNSResolutionError, UnsafeURLError, check_url_is_safe
from app.db.enums import PageOutcome

HTML_TYPES = {"text/html", "application/xhtml+xml"}
MAX_RETRIES = 2          # so at most 3 tries in total
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 4.0  # never wait longer than this between tries (also caps Retry-After)


@dataclass
class FetchResult:
    url: str                          # the URL we were asked to fetch
    final_url: str | None = None      # where we ended up after redirects
    http_status: int | None = None
    content_type: str | None = None
    byte_size: int | None = None
    html: str | None = None           # decoded body (HTML for pages; plain text for robots.txt)
    outcome: PageOutcome = PageOutcome.ERROR
    error_detail: str | None = None
    elapsed_ms: int = 0


def make_client() -> httpx.Client:
    """One HTTP client per crawl (reuses connections to the same site)."""
    return httpx.Client(
        timeout=settings.crawl_timeout_seconds,
        headers={
            "User-Agent": settings.crawl_user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
        follow_redirects=False,  # we follow redirects ourselves so each hop is SSRF-checked
        trust_env=False,         # ignore proxy / .netrc settings from the environment
    )


def fetch_page(client: httpx.Client, url: str, *, max_bytes: int | None = None, html_only: bool = True) -> FetchResult:
    """Fetch `url` with retries for temporary failures. Always returns a FetchResult."""
    started = time.perf_counter()
    max_bytes = max_bytes or settings.crawl_max_page_bytes

    for attempt in range(MAX_RETRIES + 1):
        result, retry_after = _fetch_once(client, url, max_bytes, html_only)
        if attempt == MAX_RETRIES or not _is_temporary(result):
            break
        sleep(_backoff_seconds(attempt, retry_after))

    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return result


def _is_temporary(result: FetchResult) -> bool:
    """Worth trying again? Timeouts, 'too many requests' (429) and server errors (5xx)."""
    if result.outcome == PageOutcome.TIMEOUT:
        return True
    return result.outcome == PageOutcome.HTTP_ERROR and (result.http_status == 429 or (result.http_status or 0) >= 500)


def _backoff_seconds(attempt: int, retry_after: float | None) -> float:
    """Exponential backoff (0.5s, 1s, ...) plus random jitter, honouring Retry-After, capped."""
    delay = BACKOFF_BASE_SECONDS * (2 ** attempt) + random.uniform(0, BACKOFF_BASE_SECONDS)
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, BACKOFF_CAP_SECONDS)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Retry-After header in seconds (the HTTP-date form is ignored for simplicity)."""
    try:
        return max(0.0, float(response.headers.get("retry-after", "")))
    except ValueError:
        return None


def _fetch_once(client: httpx.Client, url: str, max_bytes: int, html_only: bool) -> tuple[FetchResult, float | None]:
    """One try, following redirects by hand. Returns (result, retry_after_seconds)."""
    result = FetchResult(url=url)
    current = url
    try:
        for _hop in range(settings.crawl_max_redirects + 1):
            check_url_is_safe(current)  # raises if this hop points somewhere private
            with client.stream("GET", current) as response:
                result.final_url = str(response.url)
                result.http_status = response.status_code
                if response.is_redirect:  # 3xx with a Location header
                    current = urljoin(current, response.headers["location"])
                    continue
                _read_body(response, result, max_bytes, html_only)
                return result, _retry_after_seconds(response)
        result.outcome = PageOutcome.ERROR
        result.error_detail = f"more than {settings.crawl_max_redirects} redirects"
    except UnsafeURLError as exc:
        result.outcome = PageOutcome.BLOCKED_UNSAFE
        result.error_detail = str(exc)
    except DNSResolutionError as exc:
        result.outcome = PageOutcome.ERROR
        result.error_detail = str(exc)
    except httpx.TimeoutException as exc:
        result.outcome = PageOutcome.TIMEOUT
        result.error_detail = type(exc).__name__
    except Exception as exc:  # connection refused, TLS error, malformed response, ... never crash the crawl
        result.outcome = PageOutcome.ERROR
        result.error_detail = f"{type(exc).__name__}: {exc}"[:300]
    return result, None


def _read_body(response: httpx.Response, result: FetchResult, max_bytes: int, html_only: bool) -> None:
    """Check status and type, then stream the body up to `max_bytes`. Fills in `result`."""
    content_type = response.headers.get("content-type", "")
    result.content_type = content_type[:200] or None

    if not response.is_success:  # 4xx, 5xx (and odd ones like 304)
        result.outcome = PageOutcome.HTTP_ERROR
        result.error_detail = f"HTTP {response.status_code}"
        return

    mime = content_type.split(";")[0].strip().lower()
    if html_only and mime not in HTML_TYPES:
        result.outcome = PageOutcome.NOT_HTML
        result.error_detail = f"content type '{mime or 'missing'}'"
        return

    # Cheap early refusal when the server tells us the size up front.
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        result.outcome = PageOutcome.TOO_LARGE
        result.byte_size = int(declared)
        result.error_detail = f"declared size {declared} bytes > limit {max_bytes}"
        return

    # Stream and stop as soon as the limit is passed (the declared size can lie or be missing).
    body = bytearray()
    read_started = time.perf_counter()
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > max_bytes:
            result.outcome = PageOutcome.TOO_LARGE
            result.byte_size = len(body)
            result.error_detail = f"more than {max_bytes} bytes"
            return
        # A server dripping one byte at a time never trips the per-read timeout; cap the whole read.
        if time.perf_counter() - read_started > settings.crawl_timeout_seconds:
            raise httpx.ReadTimeout("body took too long")

    result.byte_size = len(body)
    try:
        text = body.decode(response.encoding or "utf-8", errors="replace")
    except LookupError:  # server declared a charset Python does not know
        text = body.decode("utf-8", errors="replace")

    if not text.strip():
        result.outcome = PageOutcome.EMPTY
        return
    result.html = text
    result.outcome = PageOutcome.OK
