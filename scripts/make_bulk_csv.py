"""Make sample-data/bulk_1000.csv: 1,000 SYNTHETIC rows for the intake (upload) test. Deterministic (seed 42).

    python scripts/make_bulk_csv.py

- 900 valid, unique companies on reserved `.example` domains (RFC 2606: never real websites)
- 50 invalid rows (missing name / website, not a website, wrong scheme, localhost, bad domain)
- 50 duplicates of an EARLIER row, written differently: WWW., https://, trailing slash, upper case, a path

These rows are for intake validation only - they are never crawled.
"""
import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sample-data" / "bulk_1000.csv"
rng = random.Random(42)

valid = [(f"Synthetic Co-op {i:04d}", f"company-{i:04d}.example") for i in range(1, 901)]

INVALID = [
    ("", "missing-name-{n}.example"),            # missing name
    ("Missing Website {n}", ""),                 # missing website
    ("Not A Website {n}", "not a website {n}"),  # not a URL
    ("FTP Co-op {n}", "ftp://ftp-{n}.example"),  # wrong scheme
    ("Local Co-op {n}", "http://localhost"),     # no public domain
    ("Bad Domain {n}", "-bad-{n}-.example"),     # invalid label
    ("No Dot {n}", "nodot{n}"),                  # no top-level domain
]
invalid = [(name.format(n=n), site.format(n=n)) for n in range(1, 51)
           for name, site in [INVALID[(n - 1) % len(INVALID)]]]


def variant(domain: str, k: int) -> str:
    """The same website, spelled differently (all must be recognised as the same company)."""
    return [f"https://www.{domain}", f"http://{domain}/", domain.upper(), f"www.{domain}/about",
            f"HTTPS://WWW.{domain.upper()}/"][k % 5]


rows: list[tuple[str, str]] = list(valid)
for k in range(50):  # duplicates: always placed AFTER the row they repeat
    original = rng.randrange(0, 850)
    name, domain = valid[original]
    position = rng.randrange(rows.index(valid[original]) + 1, len(rows) + 1)
    rows.insert(position, (f"{name} (again)", variant(domain, k)))
for name, site in invalid:
    rows.insert(rng.randrange(0, len(rows) + 1), (name, site))

assert len(rows) == 1000
with open(OUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["company_name", "website"])
    writer.writerows(rows)
print(f"wrote {OUT} ({len(rows)} rows: 900 valid unique, 50 invalid, 50 duplicates)")
