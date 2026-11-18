"""URL helpers shared by the crawler (and later by CSV ingest).

- normalize_page_url: one spelling per page, so we never fetch the same page twice
- canonical_domain:   one spelling per company website ("agtegra.com")
- same_site:          is this link still on the company's website?
- is_probably_page:   skip links to PDFs, images, archives, ...
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.crawler.safety import is_ip_literal

DEFAULT_PORTS = {"http": 80, "https": 443}
TRACKING_PARAMS = {"gclid", "fbclid"}  # plus anything starting with "utm_"

# One DNS label: letters, digits, hyphens; 1-63 chars; no hyphen at either end.
LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

NON_PAGE_EXTENSIONS = {
    "pdf", "jpg", "jpeg", "png", "gif", "webp", "svg", "ico", "bmp", "tif", "tiff",
    "zip", "rar", "7z", "gz", "tar",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv",
    "mp3", "mp4", "mov", "avi", "wmv", "webm",
    "css", "js", "json", "xml", "rss", "exe", "dmg",
}


def _is_tracking(param: str) -> bool:
    return param.lower().startswith("utm_") or param.lower() in TRACKING_PARAMS


def normalize_page_url(url: str) -> str | None:
    """Return one canonical spelling of a page URL, or None if it is not a usable http(s) URL.

    https://Example.com:443/about/?utm_source=x#team  ->  https://example.com/about
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port  # raises ValueError for a bad port like ":99999"
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()  # .hostname is already lower-case, without user/port
    if scheme not in DEFAULT_PORTS or not host:
        return None

    if ":" in host:  # IPv6 address: put the brackets back
        host = f"[{host}]"
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    # Keep any "user:pass@" so the SSRF check can still see (and reject) it.
    userinfo = parts.netloc.rpartition("@")[0]
    if userinfo:
        netloc = f"{userinfo}@{netloc}"

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"

    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)])
    return urlunsplit((scheme, netloc, path, query, ""))  # "" = fragment (#...) dropped


def canonical_domain(raw: str | None) -> str | None:
    """'https://WWW.Agtegra.com/about/' -> 'agtegra.com'. None if it is not a valid website domain."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw  # accept a bare "agtegra.com"

    parts = urlsplit(raw)
    if parts.scheme.lower() not in DEFAULT_PORTS or parts.username or parts.password:
        return None

    host = (parts.hostname or "").rstrip(".")  # "agtegra.com." (trailing dot) is the same name
    try:
        host = host.encode("idna").decode("ascii").lower()  # international names -> "xn--..." form
    except UnicodeError:
        return None
    if host.startswith("www."):
        host = host[4:]

    if "." not in host or len(host) > 253 or is_ip_literal(host):
        return None
    labels = host.split(".")
    if not all(LABEL_RE.match(label) for label in labels):
        return None
    if not re.search(r"[a-z]", labels[-1]):  # top-level domain must contain a letter (not "1.2.3.4")
        return None
    return host


def same_site(url: str, domain: str) -> bool:
    """True if the URL's host is the domain itself or one of its subdomains."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def is_probably_page(url: str) -> bool:
    """False for links to files we do not read (PDF, images, office docs, video, ...)."""
    last_segment = urlsplit(url).path.rsplit("/", 1)[-1].lower()
    if "." not in last_segment:
        return True  # "/about", "/products/" - no extension, assume a page
    return last_segment.rsplit(".", 1)[-1] not in NON_PAGE_EXTENSIONS
