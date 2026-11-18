"""Uploads: POST a CSV of companies; read the per-row results.

The upload only VALIDATES and STORES companies - no crawling or AI happens in the request,
so it answers in well under a second. Research starts with POST /api/runs.
"""
import hashlib

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError, not_found
from app.auth import require_reviewer
from app.config import settings
from app.db.deps import get_db
from app.db.enums import UploadRowResult
from app.db.models import Upload, UploadRow, User
from app.ratelimit import limiter
from app.schemas.common import PageParams, page_params, paginate
from app.services.ingest import MAX_CSV_BYTES, IngestError, ingest_rows, parse_csv

router = APIRouter(tags=["uploads"])


def row_json(r: UploadRow) -> dict:
    return {"row_no": r.row_no, "name": r.raw_name, "website": r.raw_url, "result": r.result,
            "error_code": r.error_code, "message": r.error_message, "company_id": r.company_id}


def upload_summary(upload: Upload) -> dict:
    return {"upload_id": upload.id, "file_name": upload.file_name, "created_at": upload.created_at,
            "counts": {"total": upload.total_rows, "accepted": upload.accepted_rows,
                       "existing": upload.existing_rows, "duplicate": upload.duplicate_rows,
                       "invalid": upload.invalid_rows}}


@router.post("/uploads", status_code=201)
@limiter.limit(settings.rate_limit_upload)
async def upload_csv(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                     user: User = Depends(require_reviewer)):
    """CSV with columns company_name, website. Returns counts + only the rows that were NOT accepted."""
    data = await file.read(MAX_CSV_BYTES + 1)  # read one byte more than allowed, to detect "too big"
    try:
        rows = parse_csv(data)
    except IngestError as exc:
        raise ApiError(400, exc.code, exc.message) from exc
    upload = ingest_rows(db, rows, uploaded_by=user.id, file_name=file.filename,
                         file_sha256=hashlib.sha256(data).hexdigest())
    problems = db.scalars(select(UploadRow).where(UploadRow.upload_id == upload.id,
                                                  UploadRow.result != UploadRowResult.ACCEPTED)
                          .order_by(UploadRow.row_no)).all()
    return {**upload_summary(upload), "rows": [row_json(r) for r in problems]}


@router.get("/uploads/{upload_id}/rows")
def upload_rows(upload_id: int, result: UploadRowResult | None = None,
                params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    if db.get(Upload, upload_id) is None:
        raise not_found("Upload", upload_id)
    stmt = select(UploadRow).where(UploadRow.upload_id == upload_id).order_by(UploadRow.row_no)
    if result:
        stmt = stmt.where(UploadRow.result == result)
    return paginate(db, stmt, params, row_json)
