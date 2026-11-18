"""Shared response helpers: one shape for every list endpoint.

    {"items": [...], "page": 1, "page_size": 50, "total": 123}
"""
from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import func, select

MAX_PAGE_SIZE = 200


@dataclass
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE)) -> PageParams:
    """FastAPI dependency: ?page=&page_size= with limits (bad values -> 422 VALIDATION_ERROR)."""
    return PageParams(page, page_size)


def page_response(items: list, params: PageParams, total: int) -> dict:
    return {"items": items, "page": params.page, "page_size": params.page_size, "total": total}


def paginate(db, stmt, params: PageParams, serialize) -> dict:
    """Run a SELECT for one page (LIMIT/OFFSET in SQL) plus a COUNT of all matches."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.limit(params.page_size).offset(params.offset)).all()
    return page_response([serialize(r) for r in rows], params, total)
