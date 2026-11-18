"""Save a crawl's pages to the `pages` table (one row per page result)."""
import hashlib

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.crawler.crawl import CrawlResult
from app.db.models import Page

URL_MAX = 2048  # matches the column size


def _clean(value: str | None) -> str | None:
    """PostgreSQL text cannot contain NUL characters; some web pages do. Drop them."""
    return value.replace("\x00", "") if value else value


def save_pages(db: Session, job_id: int, crawl_result: CrawlResult) -> list[Page]:
    """Insert one Page row per crawled page and return them.

    (job_id, url) is UNIQUE in the database. If the same job is crawled again
    (a retry after a crash), the existing row for that URL is UPDATED with the
    newer result instead of failing or creating a duplicate ("upsert").
    The caller owns the transaction (commit / rollback).
    """
    rows = {}
    for p in crawl_result.pages:
        url = p.url[:URL_MAX]
        if url in rows:
            continue  # the crawler never returns duplicates, but the DB rule must hold regardless
        text = _clean(p.text) or None
        rows[url] = {
            "job_id": job_id,
            "url": url,
            "final_url": p.final_url[:URL_MAX] if p.final_url else None,
            "depth": p.depth,
            "http_status": p.http_status,
            "content_type": p.content_type,
            "byte_size": p.byte_size,
            "outcome": str(p.outcome),
            "error_detail": _clean(p.error_detail),
            "title": _clean(p.title),
            "text_content": text,
            # Fingerprint of the stored text: spot unchanged pages between scans.
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        }
    if not rows:
        return []

    stmt = insert(Page)
    updated_columns = {name: stmt.excluded[name] for name in next(iter(rows.values())) if name not in ("job_id", "url")}
    stmt = stmt.on_conflict_do_update(
        index_elements=[Page.job_id, Page.url],
        set_={**updated_columns, "fetched_at": func.now()},
    ).returning(Page)
    # populate_existing: refresh any Page objects already loaded in this session with the new values
    return list(db.scalars(stmt, list(rows.values()), execution_options={"populate_existing": True}))
