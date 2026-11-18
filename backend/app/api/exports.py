"""Exports: the FINAL answers (human override wins) as CSV or JSON, and the corrections audit trail.

The data is read from the database first (inside the request), then streamed out in
chunks with a dated file name. Viewers and reviewers can export.
"""
import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.enums import Category, ClassStatus
from app.services.answers import ALL_CATEGORIES, company_query, final_answers_bulk, latest_finished_jobs, matches_filter
from app.services.overrides import override_history

router = APIRouter(tags=["exports"])

QUOTE_CHARS = 300
SOURCE_LABEL = {"site": "site", "rule": "rule", "human": "human", None: ""}


def _stream(chunks, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(chunks, media_type=media_type,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _filename(prefix: str, fmt: str) -> str:
    return f"{prefix}-{datetime.now(UTC):%Y-%m-%d}.{fmt}"


def _csv_chunks(header: list[str], rows: list[list]):
    """Yield the CSV text one line at a time (csv.writer handles quoting and commas)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in [header, *rows]:
        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()


def _json_chunks(items: list[dict]):
    """Yield a JSON array one item at a time."""
    yield "[\n"
    for i, item in enumerate(items):
        yield ("" if i == 0 else ",\n") + json.dumps(jsonable_encoder(item), ensure_ascii=False)
    yield "\n]\n"


def _first_quote(answer: dict) -> tuple[str, str]:
    """(source URL, quote) of the first verified quote behind an automated answer; empty for human/rule."""
    if answer["provenance"] != "site" or not answer["automated"]:
        return "", ""
    evidence = answer["automated"].get("evidence") or []
    if not evidence:
        return "", ""
    first = evidence[0]
    quote = " ".join(first["quote"].split())
    return first["source_url"], quote if len(quote) <= QUOTE_CHARS else quote[: QUOTE_CHARS - 1] + "…"


@router.get("/exports")
def export_companies(format: str = Query("csv", pattern="^(csv|json)$"), search: str | None = None,
                     category: Category | None = None, status: ClassStatus | None = None,
                     include_test: bool = True, db: Session = Depends(get_db)):
    companies = db.scalars(company_query(search, include_test)).all()
    answers = final_answers_bulk(db, [c.id for c in companies], with_evidence=True)
    companies = [c for c in companies if matches_filter(answers[c.id], category, status)]
    finished = latest_finished_jobs(db, [c.id for c in companies])

    def last_scanned(company_id):
        return finished[company_id].finished_at if company_id in finished else None

    if format == "json":
        history = override_history(db, [c.id for c in companies])
        items = [{
            "company_name": c.name, "website": c.website_url, "canonical_domain": c.canonical_domain,
            "source": c.source, "last_scanned_at": last_scanned(c.id), "answers": list(answers[c.id].values()),
            "override_history": [h for h in history if h["company_id"] == c.id],
        } for c in companies]
        return _stream(_json_chunks(items), _filename("companies", "json"), "application/json")

    header = ["company_name", "website", "canonical_domain", "source", "last_scanned_at"]
    for cat in ALL_CATEGORIES:
        header += [f"{cat}_status", f"{cat}_source", f"{cat}_evidence_url", f"{cat}_quote", f"{cat}_conflict"]
    rows = []
    for c in companies:
        scanned = last_scanned(c.id)
        row = [c.name, c.website_url, c.canonical_domain, c.source, scanned.isoformat() if scanned else ""]
        for cat in ALL_CATEGORIES:
            a = answers[c.id][cat]
            url, quote = _first_quote(a)
            row += [a["status"] or "not_scanned", SOURCE_LABEL[a["provenance"]], url, quote,
                    "yes" if a["conflict"] else "no"]
        rows.append(row)
    return _stream(_csv_chunks(header, rows), _filename("companies", "csv"), "text/csv; charset=utf-8")


@router.get("/exports/overrides")
def export_overrides(format: str = Query("csv", pattern="^(csv|json)$"), db: Session = Depends(get_db)):
    """Every correction ever made (audit trail), newest first."""
    history = override_history(db)
    if format == "json":
        return _stream(_json_chunks(history), _filename("corrections", "json"), "application/json")
    header = ["created_at", "company_name", "category", "old_status", "new_status", "reason", "reviewer_email",
              "version"]
    rows = [[h["created_at"].isoformat(), h["company_name"], h["category"], h["old_status"] or "",
             h["new_status"] or "(correction removed)", h["reason"], h["reviewer_email"], h["version"]]
            for h in history]
    return _stream(_csv_chunks(header, rows), _filename("corrections", "csv"), "text/csv; charset=utf-8")
