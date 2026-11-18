"""HTML -> clean text and links."""
from app.crawler.extract import MAX_TEXT_CHARS, extract

BASE = "https://coop.example/about/team"


def test_script_style_and_hidden_content_removed():
    html = """<html><head><title> Our   Co-op </title><style>.x{color:red}</style></head>
    <body><script>var secret = 1;</script><noscript>enable js</noscript>
    <svg><text>logo</text></svg><template><p>hidden</p></template>
    <h1>Grain   marketing</h1><p>Cash bids
    daily</p></body></html>"""
    title, text, _ = extract(html, BASE)
    assert title == "Our Co-op"
    assert "Grain marketing" in text
    assert "Cash bids daily" in text
    for removed in ("secret", "color:red", "enable js", "logo", "hidden"):
        assert removed not in text


def test_menus_removed_from_text_but_links_kept_and_footer_kept():
    html = """<header><a href="/home">Main Utilities</a></header>
    <nav><a href="/grain">Grain</a><a href="/energy">Energy</a></nav>
    <main><p>We deliver propane.</p></main>
    <footer><p>Store hours: Mon-Fri 7-5, 101 Main St</p></footer>"""
    _, text, links = extract(html, BASE)
    assert "Main Utilities" not in text and "Energy" not in text  # menu text gone
    assert "We deliver propane." in text
    assert "Store hours: Mon-Fri 7-5, 101 Main St" in text      # footer kept (store evidence)
    assert [u for u, _ in links] == ["https://coop.example/home", "https://coop.example/grain",
                                     "https://coop.example/energy"]  # menu links still followed


def test_inline_tags_stay_on_one_line_and_blocks_split_lines():
    html = ("<div><p>We buy <b>corn</b> and <a href='/soy'>soybeans</a>.</p>"
            "<ul><li>Propane</li><li>Diesel</li></ul></div>")
    _, text, _ = extract(html, BASE)
    assert text.split("\n") == ["We buy corn and soybeans.", "Propane", "Diesel"]


def test_links_resolved_and_junk_links_skipped():
    html = """<a href="/grain">Grain</a> <a href="../locations">Locations</a> <a href="https://other.example/x">Out</a>
    <a href="mailto:info@coop.example">Mail</a> <a href="tel:+15551234">Call</a>
    <a href="javascript:alert(1)">JS</a> <a href=" JavaScript:void(0)">JS2</a> <a href="#top">Top</a> <a>no href</a>"""
    _, _, links = extract(html, BASE)
    assert links == [
        ("https://coop.example/grain", "Grain"),
        ("https://coop.example/locations", "Locations"),
        ("https://other.example/x", "Out"),  # kept here; the crawler decides what is on-site
    ]


def test_broken_html_does_not_crash():
    title, text, links = extract("<html><body><div><p>Feed <b>mill<a href='/feed'>Feed</div></td></html", BASE)
    assert "Feed" in text
    assert ("https://coop.example/feed", "Feed") in links


def test_not_even_html_does_not_crash():
    assert extract("\x00\x01 just bytes <<<>>>", BASE)[1] is not None
    assert extract("", BASE) == (None, "", [])


def test_text_is_capped():
    _, text, _ = extract("<p>" + "word " * 20_000 + "</p>", BASE)
    assert len(text) == MAX_TEXT_CHARS
