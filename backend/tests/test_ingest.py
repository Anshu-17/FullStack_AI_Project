"""CSV parsing and company ingest: per-row results, file errors, scale, concurrency."""
import threading
import time

import pytest
from sqlalchemy import func, select

from app.db.models import Company, UploadRow
from app.services.ingest import MAX_ROWS, IngestError, ingest_rows, parse_csv


def rows_by_no(db, upload_id) -> dict[int, UploadRow]:
    return {r.row_no: r for r in db.scalars(select(UploadRow).where(UploadRow.upload_id == upload_id))}


# ------------------------------------------------------------------ parse_csv

def test_parse_handles_bom_and_messy_headers_and_blank_rows():
    data = "﻿  Company Name ,WEBSITE\nPrairie Co-op,prairie.example\n,,\nRiver FS, https://river.example\n"
    rows = parse_csv(data.encode("utf-8"))
    assert rows == [{"row_no": 1, "name": "Prairie Co-op", "website": "prairie.example"},
                    {"row_no": 3, "name": "River FS", "website": " https://river.example"}]


def test_missing_columns_is_a_clear_error():
    with pytest.raises(IngestError) as err:
        parse_csv(b"name,url\nA,a.example\n")
    assert err.value.code == "MISSING_COLUMNS"
    assert "company_name" in err.value.message and "website" in err.value.message


def test_not_utf8_too_big_and_too_many_rows():
    with pytest.raises(IngestError, match="UTF-8"):
        parse_csv("company_name,website\nCafé,cafe.example\n".encode("latin-1"))
    with pytest.raises(IngestError) as too_big:
        parse_csv(b"company_name,website\n" + b"x" * (2 * 1024 * 1024))
    assert too_big.value.code == "FILE_TOO_LARGE"
    many = "company_name,website\n" + "".join(f"C{i},c{i}.example\n" for i in range(MAX_ROWS + 1))
    with pytest.raises(IngestError) as too_many:
        parse_csv(many.encode())
    assert too_many.value.code == "TOO_MANY_ROWS"


# ------------------------------------------------------------------ ingest_rows

def test_each_row_gets_a_result_with_a_reason(db):
    db.add(Company(name="Old Co-op", website_url="https://old.example/", canonical_domain="old.example"))
    db.flush()
    rows = parse_csv(b"company_name,website\n"
                     b"Prairie Co-op,https://www.prairie.example/about\n"  # 1 accepted
                     b"Prairie again,prairie.example\n"                    # 2 duplicate of row 1
                     b"Old Co-op,http://old.example\n"                     # 3 existing company
                     b"No Site,\n"                                         # 4 invalid: missing website
                     b",nameless.example\n"                                # 5 invalid: missing name
                     b"Bad,not a website\n")                               # 6 invalid: bad website
    upload = ingest_rows(db, rows, file_name="t.csv")
    r = rows_by_no(db, upload.id)

    assert r[1].result == "accepted" and r[1].company_id is not None
    assert r[2].result == "duplicate" and "row 1" in r[2].error_message
    assert r[3].result == "existing" and r[3].company_id == db.scalar(
        select(Company.id).where(Company.canonical_domain == "old.example"))
    assert (r[4].result, r[4].error_code) == ("invalid", "MISSING_WEBSITE")
    assert (r[5].result, r[5].error_code) == ("invalid", "MISSING_NAME")
    assert (r[6].result, r[6].error_code) == ("invalid", "INVALID_WEBSITE")
    assert (upload.accepted_rows, upload.duplicate_rows, upload.existing_rows, upload.invalid_rows) == (1, 1, 1, 3)
    new = db.scalar(select(Company).where(Company.canonical_domain == "prairie.example"))
    assert new.website_url == "https://www.prairie.example/about"


def test_thousand_rows_with_invalid_and_duplicates_is_fast(db):
    lines = ["company_name,website"]
    for i in range(1, 1001):
        if i % 20 == 0:
            lines.append(f"Bad {i},not a site")           # 5 % invalid
        elif i % 20 == 10:
            lines.append(f"Dup {i},company{i - 1}.example")  # 5 % duplicates of the previous row
        else:
            lines.append(f"Company {i},company{i}.example")
    started = time.perf_counter()
    upload = ingest_rows(db, parse_csv("\n".join(lines).encode()), file_name="big.csv")
    elapsed = time.perf_counter() - started

    assert (upload.total_rows, upload.invalid_rows, upload.duplicate_rows, upload.accepted_rows) == (1000, 50, 50, 900)
    assert db.scalar(select(func.count()).select_from(Company)) == 900
    assert elapsed < 10, f"ingest took {elapsed:.1f} s"


def test_two_concurrent_uploads_of_the_same_company_create_it_once(fresh_db):
    """Two sessions (like two API requests) insert the same domain at the same instant."""
    start = threading.Barrier(2)
    results, errors = [], []

    def upload(name):
        try:
            with fresh_db() as s:
                start.wait()  # both threads go at once
                up = ingest_rows(s, [{"row_no": 1, "name": name, "website": "https://same.example"}])
                results.append(s.scalar(select(UploadRow.result).where(UploadRow.upload_id == up.id)))
        except Exception as exc:  # pragma: no cover - the test asserts there are none
            errors.append(exc)

    threads = [threading.Thread(target=upload, args=(n,)) for n in ("First", "Second")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)

    assert errors == []
    assert sorted(results) == ["accepted", "existing"]
    with fresh_db() as s:
        count = select(func.count()).select_from(Company).where(Company.canonical_domain == "same.example")
        assert s.scalar(count) == 1
