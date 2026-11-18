"""Saving crawl results to the pages table."""
import hashlib

import pytest
from sqlalchemy import func, select

from app.crawler.crawl import CrawledPage, CrawlResult
from app.crawler.store import save_pages
from app.db.enums import PageOutcome
from app.db.models import Company, Job, Page, PolicyVersion, Run


@pytest.fixture()
def job(db):
    db.add(PolicyVersion(version="t1", description="test", rules={}))
    company = Company(name="Coop", website_url="https://coop.example/", canonical_domain="coop.example")
    db.add(company)
    db.flush()
    run = Run(policy_version="t1")
    db.add(run)
    db.flush()
    job = Job(run_id=run.id, company_id=company.id)
    db.add(job)
    db.flush()
    return job


def crawl_result(text="Grain and agronomy services"):
    return CrawlResult(
        start_url="https://coop.example/",
        pages=[
            CrawledPage(url="https://coop.example/", final_url="https://coop.example/", http_status=200,
                        content_type="text/html", byte_size=1234, outcome=PageOutcome.OK, depth=0,
                        title="Coop", text=text),
            CrawledPage(url="https://coop.example/private", outcome=PageOutcome.ROBOTS_DISALLOWED, depth=1,
                        error_detail="disallowed by robots.txt"),
        ],
    )


def test_pages_saved_with_job_outcome_and_text_hash(db, job):
    saved = save_pages(db, job.id, crawl_result())
    assert len(saved) == 2

    rows = {p.url: p for p in db.scalars(select(Page).where(Page.job_id == job.id))}
    home = rows["https://coop.example/"]
    assert home.outcome == "ok"
    assert home.http_status == 200
    assert home.title == "Coop"
    assert home.text_content == "Grain and agronomy services"
    assert home.content_sha256 == hashlib.sha256(b"Grain and agronomy services").hexdigest()

    blocked = rows["https://coop.example/private"]
    assert blocked.outcome == "robots_disallowed"
    assert blocked.text_content is None and blocked.content_sha256 is None


def test_saving_the_same_job_again_updates_instead_of_duplicating(db, job):
    first = save_pages(db, job.id, crawl_result("old text"))
    second = save_pages(db, job.id, crawl_result("new text"))  # e.g. the job was retried

    assert db.scalar(select(func.count()).select_from(Page).where(Page.job_id == job.id)) == 2
    home_first = next(p for p in first if p.depth == 0)
    home_second = next(p for p in second if p.depth == 0)
    assert home_first.id == home_second.id  # same row, updated in place
    assert home_second.text_content == "new text"


def test_nul_characters_are_removed(db, job):
    saved = save_pages(db, job.id, crawl_result("bad\x00text"))
    assert next(p for p in saved if p.depth == 0).text_content == "badtext"


def test_nothing_to_save(db, job):
    assert save_pages(db, job.id, CrawlResult(start_url="https://coop.example/")) == []
