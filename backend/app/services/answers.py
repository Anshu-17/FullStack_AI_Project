"""The FINAL answer per company and category: "human override wins".

For each category:
1. Automated answer = the classification from the company's latest finished job
   (status completed or review_required).
2. If the latest override (highest version) has a new_status, that is the final answer,
   with provenance "human". (new_status NULL = override removed -> automated answer again.)
3. Never scanned -> status None ("not scanned yet"), which is NOT the same as "not_found".

The automated answer and its evidence are always returned alongside, so a reviewer can
compare, and `conflict` is True when the human and the latest scan disagree.
"""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import selectinload

from app.db.enums import Category, JobStatus
from app.db.models import Classification, Job, Override, Page

ALL_CATEGORIES = [str(c) for c in Category]  # accounting + the 6 site categories
FINISHED = (JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED)


def latest_finished_jobs(db, company_ids: list[int]) -> dict[int, Job]:
    """company_id -> its most recently finished job (DISTINCT ON keeps the first row per company)."""
    if not company_ids:
        return {}
    jobs = db.scalars(
        select(Job).where(Job.company_id.in_(company_ids), Job.status.in_(FINISHED))
        .ext(distinct_on(Job.company_id))  # DISTINCT ON: first row per company
        .order_by(Job.company_id, Job.finished_at.desc().nulls_last(), Job.id.desc())
    ).all()
    return {j.company_id: j for j in jobs}


def latest_overrides(db, company_ids: list[int]) -> dict[tuple[int, str], Override]:
    """(company_id, category) -> highest-version override (it may be a removal: new_status NULL)."""
    if not company_ids:
        return {}
    rows = db.scalars(
        select(Override).where(Override.company_id.in_(company_ids))
        .order_by(Override.company_id, Override.category, Override.version.desc())
    ).all()
    latest: dict[tuple[int, str], Override] = {}
    for o in rows:
        latest.setdefault((o.company_id, o.category), o)
    return latest


def _automated(c: Classification, with_evidence: bool, page_times: dict) -> dict:
    data = {
        "classification_id": c.id, "job_id": c.job_id, "status": c.status, "provenance": c.provenance,
        "explanation": c.explanation, "confidence": float(c.confidence) if c.confidence is not None else None,
        "model_provider": c.model_provider, "model_name": c.model_name,
        "prompt_version": c.prompt_version, "policy_version": c.policy_version,
        "conflicts_with_override_at_scan": c.conflicts_with_override, "created_at": c.created_at,
    }
    if with_evidence:
        data["evidence"] = [{"quote": e.quote, "source_url": e.source_url, "quote_verified": e.quote_verified,
                             "page_id": e.page_id, "fetched_at": page_times.get(e.page_id)}
                            for e in c.evidence if e.quote_verified]
    return data


def final_answers_bulk(db, company_ids: list[int], with_evidence: bool = False) -> dict[int, dict[str, dict]]:
    """company_id -> {category -> answer}. Three queries in total, whatever the number of companies."""
    jobs = latest_finished_jobs(db, company_ids)
    stmt = select(Classification).where(Classification.job_id.in_([j.id for j in jobs.values()]))
    if with_evidence:
        stmt = stmt.options(selectinload(Classification.evidence))
    classifications = db.scalars(stmt).all() if jobs else []
    by_key = {(c.company_id, c.category): c for c in classifications}

    page_times = {}
    if with_evidence:
        page_ids = {e.page_id for c in classifications for e in c.evidence if e.page_id}
        if page_ids:
            page_times = dict(db.execute(select(Page.id, Page.fetched_at).where(Page.id.in_(page_ids))).all())

    overrides = latest_overrides(db, company_ids)
    result: dict[int, dict[str, dict]] = {}
    for company_id in company_ids:
        answers = {}
        for category in ALL_CATEGORIES:
            c = by_key.get((company_id, category))
            o = overrides.get((company_id, category))
            automated = _automated(c, with_evidence, page_times) if c else None
            human = None
            if o is not None and o.new_status is not None:
                human = {"status": o.new_status, "reason": o.reason, "reviewer_id": o.reviewer_id,
                         "version": o.version, "created_at": o.created_at}

            if human:
                status, provenance, explanation = human["status"], "human", human["reason"]
            elif automated:
                status, provenance, explanation = automated["status"], automated["provenance"], automated["explanation"]
            else:
                status, provenance, explanation = None, None, "Not scanned yet."

            answers[category] = {
                "category": category, "status": status, "provenance": provenance, "explanation": explanation,
                "automated": automated, "override": human,
                "override_version": o.version if o else 0,  # the version a reviewer must build on (Hour 5)
                "conflict": bool(human and automated and human["status"] != automated["status"]),
            }
        result[company_id] = answers
    return result


def final_answers(db, company_id: int, with_evidence: bool = True) -> dict[str, dict]:
    return final_answers_bulk(db, [company_id], with_evidence)[company_id]
