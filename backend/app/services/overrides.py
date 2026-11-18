"""Reviewer corrections with optimistic locking (scenario G: two reviewers edit the same answer).

Every correction of (company, category) gets the next version number: 1, 2, 3, ...
The reviewer's screen remembers which version it showed (`expected_version`, 0 = no
correction yet). On save:

- expected_version == current version -> save as version + 1
- expected_version != current version -> 409 VERSION_CONFLICT: someone else saved first;
  we say who, when and what the answer is now, and nothing is overwritten.

If two saves arrive at the same instant, both see the same current version, but the
database's UNIQUE (company_id, category, version) rule lets only ONE insert succeed; the
other gets the same 409. Rows are never updated or deleted (full audit history).
new_status = None means "remove my correction, show the automated answer again".
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError
from app.db.models import Company, Override, User
from app.services.answers import final_answers


def latest_override(db, company_id: int, category: str) -> Override | None:
    return db.scalar(select(Override).where(Override.company_id == company_id, Override.category == category)
                     .order_by(Override.version.desc()).limit(1))


def version_conflict(db, company_id: int, category: str) -> ApiError:
    """409 with what the reviewer needs to know: who changed it, when, and the answer now."""
    latest = latest_override(db, company_id, category)
    answer = final_answers(db, company_id, with_evidence=False)[category]
    who = db.get(User, latest.reviewer_id).email if latest else None
    return ApiError(409, "VERSION_CONFLICT",
                    "Someone else changed this answer after you opened it. Reload to see the latest version.",
                    {"current_version": latest.version if latest else 0, "changed_by": who,
                     "changed_at": latest.created_at.isoformat() if latest else None,
                     "current_status": answer["status"]})


def create_override(db, company_id: int, category: str, new_status: str | None, reason: str,
                    expected_version: int, reviewer: User) -> Override:
    latest = latest_override(db, company_id, category)
    current_version = latest.version if latest else 0
    if expected_version != current_version:
        raise version_conflict(db, company_id, category)

    shown = final_answers(db, company_id, with_evidence=False)[category]  # what the reviewer saw
    if new_status is None and shown["provenance"] != "human":
        raise ApiError(422, "NOTHING_TO_REMOVE", "There is no correction to remove for this category.")

    row = Override(
        company_id=company_id, category=category, old_status=shown["status"], new_status=new_status,
        reason=reason.strip(), reviewer_id=reviewer.id, version=expected_version + 1,
        based_on_classification_id=shown["automated"]["classification_id"] if shown["automated"] else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        # Lost the race: another reviewer inserted this version a moment earlier.
        db.rollback()
        raise version_conflict(db, company_id, category) from exc
    return row


def override_json(o: Override, email: str | None, company_name: str | None = None) -> dict:
    data = {"id": o.id, "company_id": o.company_id, "category": o.category, "old_status": o.old_status,
            "new_status": o.new_status, "reason": o.reason, "reviewer_email": email, "version": o.version,
            "based_on_classification_id": o.based_on_classification_id, "created_at": o.created_at}
    if company_name is not None:
        data["company_name"] = company_name
    return data


def override_history(db, company_ids: list[int] | None = None) -> list[dict]:
    """All corrections (optionally of some companies), newest first, with reviewer email and company name."""
    stmt = (select(Override, User.email, Company.name).join(User, User.id == Override.reviewer_id)
            .join(Company, Company.id == Override.company_id)
            .order_by(Override.created_at.desc(), Override.id.desc()))
    if company_ids is not None:
        stmt = stmt.where(Override.company_id.in_(company_ids))
    return [override_json(o, email, name) for o, email, name in db.execute(stmt).all()]
