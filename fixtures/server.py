"""Local fixture websites for controlled tests - Python standard library only.

    python fixtures/server.py            # serves on 127.0.0.1:8765

Every fixture company has its own domain <site>.fixture.test (".test" is reserved and can never be
a real website). The backend's TEST-ONLY setting CRAWL_FIXTURE_SERVER=127.0.0.1:8765 sends those
requests here with the original Host header; this server picks the site from that header:

    Host: clear-coop.fixture.test      -> fixtures/sites/clear-coop/
    Host: clear-coop-017.fixture.test  -> fixtures/sites/clear-coop/   (numbered copies for load tests)

Pages:  /  -> index.html,  /grain -> grain.html,  /robots.txt -> robots.txt (404 if the site has none)

Special behaviour (deterministic):
    redirect-to-private  every page answers 302 -> http://10.0.0.5/admin (a private address)
    broken-site          every page answers 500
    empty-site           the homepage is 200 with an empty body
    /__slow?seconds=N    any site: waits N seconds (default 8), then a small page
    /__500               any site: 500
"""
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SITES = Path(__file__).parent / "sites"
SUFFIX = ".fixture.test"
HOST, PORT = "127.0.0.1", 8765


def site_for(host_header: str) -> str | None:
    """'clear-coop-017.fixture.test:80' -> 'clear-coop' (None if unknown)."""
    host = host_header.split(":")[0].lower()
    if not host.endswith(SUFFIX):
        return None
    label = host[: -len(SUFFIX)]
    for name in (label, re.sub(r"-\d+$", "", label)):
        if name and (SITES / name).is_dir():
            return name
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "FixtureServer/1.0"

    def send(self, status: int, body: bytes = b"", content_type: str = "text/html; charset=utf-8",
             headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):  # noqa: N802 (name required by BaseHTTPRequestHandler)
        self.do_GET()

    def do_GET(self):  # noqa: N802
        site = site_for(self.headers.get("Host", ""))
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"

        if site is None:
            return self.send(404, b"<h1>Unknown fixture site</h1>")
        # robots.txt first, for EVERY site: a broken / redirecting homepage should be what the crawler
        # sees (if robots.txt itself failed, RFC 9309 says "disallow everything" and nothing else is fetched).
        if path == "/robots.txt":
            robots = SITES / site / "robots.txt"
            return self.send(200, robots.read_bytes(), "text/plain") if robots.exists() else self.send(404)
        if path == "/__slow":
            time.sleep(float(parse_qs(url.query).get("seconds", ["8"])[0]))
            return self.send(200, b"<html><body><p>This page was slow on purpose.</p></body></html>")
        if path == "/__500" or site == "broken-site":
            return self.send(500, b"<h1>Internal Server Error</h1>")
        if site == "redirect-to-private":
            return self.send(302, headers={"Location": "http://10.0.0.5/admin"})
        if site == "empty-site" and path == "/":
            return self.send(200, b"")

        name = "index" if path == "/" else path.lstrip("/").replace("/", "_")
        page = SITES / site / f"{name}.html"
        if page.exists():
            return self.send(200, page.read_bytes())
        return self.send(404, b"<h1>Not found</h1>")

    def log_message(self, fmt, *args):  # one short line per request
        sys.stderr.write(f"{self.headers.get('Host', '-')} {fmt % args}\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"fixture server on http://{HOST}:{port} - sites: {sorted(p.name for p in SITES.iterdir() if p.is_dir())}")
    ThreadingHTTPServer((HOST, port), Handler).serve_forever()
