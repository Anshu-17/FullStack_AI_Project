"""Companies in: parse a CSV and turn rows into companies (plain functions, no web code).

Every row gets exactly one result:
- accepted  - new company created
- existing  - valid, but the company is already in the database (linked, not duplicated)
- duplicate - the same website appears earlier in THIS file (we say which row)
- invalid   - missing / bad value (we say why)

Concurrency: companies are inserted with INSERT ... ON CONFLICT (canonical_domain) DO NOTHING.
If two uploads add the same company at the same moment, the database lets exactly one insert
win; the other finds the existing row. No duplicate, no crash.
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.crawler.urls import canonical_domain, normalize_page_url
from app.db.enums import CompanySource, UploadRowResult
from app.db.models import Company, Upload, UploadRow

MAX_CSV_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_ROWS = 5_000
MAX_NAME_CHARS = 300
REQUIRED_COLUMNS = ("company_name", "website")


class IngestError(Exception):
    """The FILE is unusable (too big, not UTF-8, missing columns). Becomes a 400 response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _header_key(header: str) -> str:
    """'  Company Name ' -> 'company_name' (case- and space-insensitive headers)."""
    return "_".join((header or "").strip().lower().replace("-", " ").split())


def parse_csv(data: bytes) -> list[dict]:
    """CSV bytes -> [{"row_no", "name", "website"}]. Raises IngestError for an unusable file."""
    if len(data) > MAX_CSV_BYTES:
        raise IngestError("FILE_TOO_LARGE", f"The file is larger than {MAX_CSV_BYTES // (1024 * 1024)} MB.")
    try:
        text = data.decode("utf-8-sig")  # "-sig" removes a byte-order mark (Excel adds one) if present
    except UnicodeDecodeError as exc:
        raise IngestError("NOT_UTF8", "The file must be UTF-8 encoded (in Excel: Save As 'CSV UTF-8').") from exc

    reader = csv.reader(io.StringIO(text))
    headers = [_header_key(h) for h in next(reader, [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise IngestError("MISSING_COLUMNS", f"Required column(s) missing: {', '.join(missing)}. "
                          f"Found: {', '.join(h for h in headers if h) or 'none'}. "
                          "The first line must contain the headers company_name and website.")
    name_col, website_col = headers.index("company_name"), headers.index("website")

    rows = []
    for row_no, values in enumerate(reader, start=1):  # row 1 = first data row
        if not any(v.strip() for v in values):
            continue  # fully blank line
        if len(rows) >= MAX_ROWS:
            raise IngestError("TOO_MANY_ROWS", f"The file has more than {MAX_ROWS} rows. Split it into smaller files.")
        rows.append({
            "row_no": row_no,
            "name": values[name_col] if name_col < len(values) else "",
            "website": values[website_col] if website_col < len(values) else "",
        })
    return rows


def _check_row(name: str, website: str) -> tuple[str | None, str | None, str | None]:
    """(error_code, error_message, domain). error_code is None when the row is valid."""
    if not name:
        return "MISSING_NAME", "Company name is empty.", None
    if len(name) > MAX_NAME_CHARS:
        return "NAME_TOO_LONG", f"Company name is longer than {MAX_NAME_CHARS} characters.", None
    if not website:
        return "MISSING_WEBSITE", "Website is empty.", None
    domain = canonical_domain(website)
    if not domain:
        return "INVALID_WEBSITE", f"'{website[:100]}' is not a valid website address.", None
    return None, None, domain


def _insert_or_get_company(db, name: str, website: str, domain: str, source: str) -> tuple[int, bool]:
    """(company_id, created). Safe when another upload inserts the same domain at the same time."""
    start_url = normalize_page_url(website if "://" in website else f"https://{website}")
    company_id = db.scalar(
        insert(Company).values(name=name, website_url=start_url, canonical_domain=domain, source=source)
        .on_conflict_do_nothing(index_elements=[Company.canonical_domain])
        .returning(Company.id)
    )
    if company_id is not None:
        return company_id, True
    # Someone (an earlier upload, or a concurrent one that just committed) already has it.
    return db.scalar(select(Company.id).where(Company.canonical_domain == domain)), False


def ingest_rows(db, rows: list[dict], uploaded_by=None, file_name=None, file_sha256=None,
                source: str = CompanySource.USER) -> Upload:
    """Create the Upload + one UploadRow per row (+ new companies) in ONE transaction.

    source labels NEW companies: user (real) or fixture / synthetic (test data). An existing company
    keeps its label.
    """
    upload = Upload(uploaded_by=uploaded_by, file_name=file_name, file_sha256=file_sha256, total_rows=len(rows))
    db.add(upload)
    db.flush()  # get upload.id

    first_row_for_domain: dict[str, int] = {}
    counts = dict.fromkeys(UploadRowResult, 0)
    for row in rows:
        name, website = (row.get("name") or "").strip(), (row.get("website") or "").strip()
        result = UploadRow(upload_id=upload.id, row_no=row["row_no"], raw_name=name or None, raw_url=website or None)

        error_code, error_message, domain = _check_row(name, website)
        if error_code:
            result.result, result.error_code, result.error_message = UploadRowResult.INVALID, error_code, error_message
        elif domain in first_row_for_domain:
            result.result, result.error_code = UploadRowResult.DUPLICATE, "DUPLICATE_IN_FILE"
            result.error_message = f"Same website as row {first_row_for_domain[domain]} ({domain})."
        else:
            first_row_for_domain[domain] = row["row_no"]
            result.company_id, created = _insert_or_get_company(db, name, website, domain, str(source))
            result.result = UploadRowResult.ACCEPTED if created else UploadRowResult.EXISTING
            if not created:
                result.error_message = f"Company with website {domain} already exists; linked to it."

        counts[result.result] += 1
        db.add(result)

    upload.accepted_rows = counts[UploadRowResult.ACCEPTED]
    upload.existing_rows = counts[UploadRowResult.EXISTING]
    upload.duplicate_rows = counts[UploadRowResult.DUPLICATE]
    upload.invalid_rows = counts[UploadRowResult.INVALID]
    db.commit()
    return upload
