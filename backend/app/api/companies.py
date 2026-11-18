"""Companies: add one, list with final answers, details with evidence and scan history, rescan."""
from fastapi import APIRouter, Depends, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.api.errors import ApiError, not_found
from app.api.runs import run_created_response
from app.db.deps import get_db
from app.db.enums import Category, ClassStatus, UploadRowResult
from app.db.models import Company, Job, UploadRow
from app.schemas.common import PageParams, page_params, page_response
from app.services.answers import final_answers, final_answers_bulk, latest_finished_jobs
from app.services.ingest import ingest_rows
from app.services.runs import create_run

router = APIRouter(tags=["companies"])


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    website: str = Field(min_length=1, max_length=2048)


def company_json(c: Company) -> dict:
    return {"id": c.id, "name": c.name, "website_url": c.website_url, "canonical_domain": c.canonical_domain,
            "created_at": c.created_at}


def job_json(j: Job | None) -> dict | None:
    if j is None:
        return None
    return {"id": j.id, "run_id": j.run_id, "status": j.status, "attempt_count": j.attempt_count,
            "last_error_code": j.last_error_code, "created_at": j.created_at,
            "started_at": j.started_at, "finished_at": j.finished_at}


@router.post("/companies")
def add_company(body: CompanyIn, db: Session = Depends(get_db)):
    """Single company. 201 if new, 200 if the website already exists (no duplicate is created)."""
    upload = ingest_rows(db, [{"row_no": 1, "name": body.name, "website": body.website}])
    row = db.scalar(select(UploadRow).where(UploadRow.upload_id == upload.id))
    if row.result == UploadRowResult.INVALID:
        raise ApiError(422, "VALIDATION_ERROR", row.error_message, {"fields": [{"field": "body.website"
                       if row.error_code.endswith("WEBSITE") else "body.name", "message": row.error_message}]})
    created = row.result == UploadRowResult.ACCEPTED
    body_json = {"created": created, "company": company_json(db.get(Company, row.company_id))}
    return JSONResponse(status_code=201 if created else 200, content=jsonable_encoder(body_json))


def _latest_jobs(db, company_ids: list[int]) -> dict[int, Job]:
    """Most recent job of each company, whatever its status."""
    if not company_ids:
        return {}
    # DISTINCT ON (company_id) + ORDER BY id DESC = the newest job of each company
    jobs = db.scalars(select(Job).where(Job.company_id.in_(company_ids)).ext(distinct_on(Job.company_id))
                      .order_by(Job.company_id, Job.id.desc())).all()
    return {j.company_id: j for j in jobs}


@router.get("/companies")
def list_companies(search: str | None = None, category: Category | None = None,
                   status: ClassStatus | None = None, params: PageParams = Depends(page_params),
                   db: Session = Depends(get_db)):
    """Companies with their FINAL answer per category (human override wins).

    Filters: search (name or domain); category + status (final answer for that category);
    status alone (any category has it); category alone (that category has been answered).
    """
    stmt = select(Company).order_by(Company.name, Company.id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Company.name.ilike(like), Company.canonical_domain.ilike(like)))

    if category is None and status is None:  # no answer filter: paginate in SQL
        total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        companies = db.scalars(stmt.limit(params.page_size).offset(params.offset)).all()
        answers = final_answers_bulk(db, [c.id for c in companies])
    else:  # the final answer depends on overrides, so filter in Python, then paginate
        all_companies = db.scalars(stmt).all()
        answers = final_answers_bulk(db, [c.id for c in all_companies])

        def keep(c: Company) -> bool:
            a = answers[c.id]
            if category and status:
                return a[category]["status"] == status
            if status:
                return any(x["status"] == status for x in a.values())
            return a[category]["status"] is not None

        matching = [c for c in all_companies if keep(c)]
        total, companies = len(matching), matching[params.offset: params.offset + params.page_size]

    ids = [c.id for c in companies]
    latest, finished = _latest_jobs(db, ids), latest_finished_jobs(db, ids)
    items = [{
        **company_json(c),
        "answers": {cat: {"status": a["status"], "provenance": a["provenance"], "conflict": a["conflict"]}
                    for cat, a in answers[c.id].items()},
        "latest_job": job_json(latest.get(c.id)),
        "last_scanned_at": finished[c.id].finished_at if c.id in finished else None,
    } for c in companies]
    return page_response(items, params, total)


@router.get("/companies/{company_id}")
def company_detail(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise not_found("Company", company_id)
    jobs = db.scalars(select(Job).where(Job.company_id == company_id).order_by(Job.id.desc())).all()
    return {
        **company_json(company),
        "answers": list(final_answers(db, company_id).values()),
        "scan_history": [job_json(j) for j in jobs],
    }


@router.post("/companies/{company_id}/rescan", status_code=201)
def rescan(company_id: int, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
           db: Session = Depends(get_db)):
    if db.get(Company, company_id) is None:
        raise not_found("Company", company_id)
    run, created, skipped = create_run(db, [company_id], idempotency_key, source="rescan")
    return run_created_response(run, created, skipped)
