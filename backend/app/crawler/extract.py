"""HTML -> (title, clean visible text, links).

Page text is untrusted DATA. We only store it; nothing here (or anywhere in the
crawler) follows instructions written on a page.
"""
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.log_config import get_logger

log = get_logger("crawler.extract")

# Tags whose content is not visible text (code, styling, embedded documents).
NON_TEXT_TAGS = ["script", "style", "noscript", "svg", "iframe", "template"]
# Block elements start a new line of text; inline ones (<b>, <a>, <span>) don't.
BLOCK_TAGS = [
    "title", "p", "div", "br", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "tr", "td", "th", "section", "article", "header", "footer", "nav", "main", "aside",
    "blockquote", "pre", "address", "form", "label", "option", "figcaption",
]
BREAK = "\x1e"  # invisible "record separator" character used as a temporary line-break marker
SKIP_LINK_PREFIXES = ("mailto:", "tel:", "javascript:", "data:", "#")
MAX_TEXT_CHARS = 50_000
MAX_TITLE_CHARS = 300
MAX_LINK_TEXT_CHARS = 200


def extract(html: str, base_url: str) -> tuple[str | None, str, list[tuple[str, str]]]:
    """Return (title, text, [(absolute_url, link_text), ...]). Never raises."""
    try:
        return _extract(html, base_url)
    except Exception as exc:  # BeautifulSoup is tolerant, but never let one page break the crawl
        log.warning("extract.failed", url=base_url, error=type(exc).__name__)
        return None, "", []


def _extract(html: str, base_url: str) -> tuple[str | None, str, list[tuple[str, str]]]:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(NON_TEXT_TAGS):
        tag.decompose()  # remove the tag and everything inside it

    title = None
    if soup.title:
        title = " ".join(soup.title.get_text(" ").split())[:MAX_TITLE_CHARS] or None

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.lower().startswith(SKIP_LINK_PREFIXES):
            continue
        try:
            absolute = urljoin(base_url, href)  # "/about" -> "https://site.com/about"
        except ValueError:  # malformed href such as "http://[broken"
            continue
        link_text = " ".join(a.get_text(" ").split())[:MAX_LINK_TEXT_CHARS]
        links.append((absolute, link_text))

    # Text: one line per block element. Newlines inside the HTML source are just
    # formatting, so ALL whitespace inside a block collapses to single spaces
    # ("Cash bids\n   daily" -> "Cash bids daily"). Blank lines are dropped.
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before(BREAK)
        tag.insert_after(BREAK)
    blocks = (" ".join(block.split()) for block in soup.get_text().split(BREAK))
    text = "\n".join(block for block in blocks if block)[:MAX_TEXT_CHARS]
    return title, text, links
