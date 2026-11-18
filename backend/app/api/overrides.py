"""Reviewer corrections: POST a correction (optimistic locking), GET the history."""
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.errors import not_found
from app.auth import require_reviewer
from app.db.deps import get_db
from app.db.enums import Category
from app.db.models import Company, User
from app.services.answers import final_answers
from app.services.overrides import create_override, override_history

router = APIRouter(tags=["corrections"])


class OverrideIn(BaseModel):
    category: Category  # all 7, including accounting (a human may correct the rule's answer; the AI never can)
    new_status: Literal["yes", "possible", "not_found"] | None  # None = remove the correction
    reason: str = Field(min_length=3, max_length=1000)
    expected_version: int = Field(ge=0, description="The version shown on screen; 0 when there is no correction yet")


@router.post("/companies/{company_id}/overrides", status_code=201)
def correct(company_id: int, body: OverrideIn, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    if db.get(Company, company_id) is None:
        raise not_found("Company", company_id)
    override = create_override(db, company_id, str(body.category), body.new_status, body.reason,
                               body.expected_version, user)
    answer = final_answers(db, company_id)[str(body.category)]
    return JSONResponse(status_code=201, content=jsonable_encoder(
        {"override": {"id": override.id, "version": override.version, "old_status": override.old_status,
                      "new_status": override.new_status}, "answer": answer}))


@router.get("/companies/{company_id}/overrides")
def history(company_id: int, db: Session = Depends(get_db)):
    if db.get(Company, company_id) is None:
        raise not_found("Company", company_id)
    return {"items": override_history(db, [company_id])}
