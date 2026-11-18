"""URL helpers: one spelling per page and per company domain."""
import pytest

from app.crawler.urls import canonical_domain, is_probably_page, normalize_page_url, same_site


def test_same_page_spelled_differently_normalizes_to_one_url():
    variants = [
        "https://coop.example/about",
        "https://coop.example/about/",
        "https://coop.example/about#team",
        "HTTPS://COOP.example:443/about/",
        "https://coop.example/about?utm_source=mail&utm_medium=x&gclid=1&fbclid=2",
    ]
    assert {normalize_page_url(v) for v in variants} == {"https://coop.example/about"}


def test_normalize_keeps_meaningful_parts():
    assert normalize_page_url("https://coop.example/") == "https://coop.example/"  # root keeps its "/"
    assert normalize_page_url("https://coop.example") == "https://coop.example/"
    assert normalize_page_url("http://coop.example:8080/a?id=7") == "http://coop.example:8080/a?id=7"
    assert normalize_page_url("https://coop.example/Products") == "https://coop.example/Products"  # path case kept


@pytest.mark.parametrize("bad", ["ftp://coop.example/", "mailto:x@coop.example", "/relative/path", "http://:80/", ""])
def test_normalize_rejects_unusable_urls(bad):
    assert normalize_page_url(bad) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://WWW.Agtegra.com/about/", "agtegra.com"),
        ("agtegra.com", "agtegra.com"),
        ("  http://agtegra.com  ", "agtegra.com"),
        ("https://shop.agtegra.com", "shop.agtegra.com"),
        ("agtegra.com.", "agtegra.com"),
    ],
)
def test_canonical_domain_valid(raw, expected):
    assert canonical_domain(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", None, "localhost", "ftp://agtegra.com", "http://10.0.0.5", "not a domain", "-bad-.com", "http://user:pw@agtegra.com"],
)
def test_canonical_domain_invalid(raw):
    assert canonical_domain(raw) is None


def test_same_site():
    assert same_site("https://coop.example/a", "coop.example")
    assert same_site("https://www.coop.example/a", "coop.example")
    assert same_site("https://shop.coop.example/a", "coop.example")
    assert not same_site("https://other.example/a", "coop.example")
    assert not same_site("https://evilcoop.example/a", "coop.example")  # suffix match must be a whole label


@pytest.mark.parametrize("url", ["https://c.example/report.pdf", "https://c.example/logo.PNG", "https://c.example/a.docx",
                                 "https://c.example/v.mp4", "https://c.example/files.zip", "https://c.example/s.xlsx"])
def test_files_are_not_pages(url):
    assert not is_probably_page(url)


@pytest.mark.parametrize("url", ["https://c.example/", "https://c.example/about", "https://c.example/grain.html",
                                 "https://c.example/locations.php", "https://c.example/v1.2/agronomy"])
def test_pages_are_pages(url):
    assert is_probably_page(url)
