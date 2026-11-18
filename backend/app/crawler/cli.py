"""Try the crawler on a real website (no database):

    python -m app.crawler.cli https://www.example.com
    python -m app.crawler.cli https://www.example.com --quiet   # table only, no per-page logs
"""
import argparse
import logging
import sys

import structlog

from app.crawler.crawl import crawl_site
from app.log_config import setup_logging


def short(value, width: int) -> str:
    """Fit a value into a fixed-width column."""
    text = " ".join(str(value if value is not None else "-").split())
    return text if len(text) <= width else text[: width - 1] + "~"


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl one website and print what was collected.")
    parser.add_argument("url")
    parser.add_argument("--quiet", action="store_true", help="hide the per-page log lines")
    args = parser.parse_args()

    sys.stdout.reconfigure(errors="replace")  # web text may contain characters the console can't show
    setup_logging()
    if args.quiet:
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
        logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs every request at INFO

    result = crawl_site(args.url)

    print()
    print(f"{'URL':<55} {'OUTCOME':<18} {'STATUS':>6} {'BYTES':>9}  {'WHY CHOSEN':<38}  TEXT (first 60 chars)")
    print("-" * 215)
    for p in result.pages:
        print(f"{short(p.url, 55):<55} {short(p.outcome, 18):<18} {short(p.http_status, 6):>6} "
              f"{short(p.byte_size, 9):>9}  {short(p.reason, 38):<38}  {short(p.text or p.error_detail, 60)}")
    print("-" * 215)
    print(f"sitemap files: {result.sitemap_files or 'none'} | new candidates from sitemap: {result.sitemap_candidates}")
    ok = sum(1 for p in result.pages if p.outcome == "ok")
    text_chars = sum(len(p.text or "") for p in result.pages)
    print(f"pages: {len(result.pages)} (ok: {ok}) | text chars: {text_chars} | bytes: {result.total_bytes} | "
          f"time: {result.elapsed_ms} ms | stopped: {result.stopped_reason}")


if __name__ == "__main__":
    main()
