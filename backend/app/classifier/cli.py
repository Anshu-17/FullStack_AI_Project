"""End-to-end run for ONE website, before the worker exists:

    python -m app.classifier.cli https://www.example.com --name "Example Co-op" [--quiet]

Creates (or reuses) the company, creates a run + job, crawls and saves pages,
classifies, sets the job status, and prints the results. Uses the real database
from DATABASE_URL and the AI providers configured in .env.
"""
import argparse
import logging
import sys
import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.classifier.pipeline import AIUnavailableError, NoContentError, classify_job
from app.classifier.taxonomy import POLICY_VERSION
from app.crawler.crawl import crawl_site
from app.crawler.store import save_pages
from app.crawler.urls import canonical_domain, normalize_page_url
from app.db.enums import JobStatus, RunStatus
from app.db.models import AIUsage, Classification, Company, Job, PolicyVersion, Run
from app.db.session import SessionLocal
from app.log_config import setup_logging


def short(value, width: int) -> str:
    text = " ".join(str(value if value is not None else "-").split())
    return text if len(text) <= width else text[: width - 1] + "~"


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl and classify one company website.")
    parser.add_argument("url")
    parser.add_argument("--name", help="company name (default: the domain)")
    parser.add_argument("--quiet", action="store_true", help="hide log lines")
    args = parser.parse_args()

    sys.stdout.reconfigure(errors="replace")
    setup_logging()
    if args.quiet:
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
        logging.getLogger("httpx").setLevel(logging.WARNING)

    domain = canonical_domain(args.url)
    start_url = normalize_page_url(args.url if "://" in args.url else f"https://{args.url}")
    if not domain or not start_url:
        sys.exit(f"Not a valid website: {args.url}")

    started = time.perf_counter()
    with SessionLocal() as db:
        if db.get(PolicyVersion, POLICY_VERSION) is None:
            sys.exit(f"Policy {POLICY_VERSION} missing - run: python -m app.db.seed")

        company = db.scalar(select(Company).where(Company.canonical_domain == domain))
        if company is None:
            company = Company(name=args.name or domain, website_url=start_url, canonical_domain=domain)
            db.add(company)
        now = datetime.now(UTC)
        run = Run(policy_version=POLICY_VERSION, status=RunStatus.RUNNING, total_items=1, started_at=now,
                  config={"source": "cli"})
        db.add(run)
        db.flush()
        job = Job(run_id=run.id, company=company, status=JobStatus.RUNNING, attempt_count=1, started_at=now)
        db.add(job)
        db.commit()
        print(f"company #{company.id} {company.name} ({domain}) | run #{run.id} | job #{job.id}")

        crawl = crawl_site(company.website_url)
        save_pages(db, job.id, crawl)
        db.commit()
        ok_pages = sum(1 for p in crawl.pages if p.outcome == "ok")
        print(f"crawl: {len(crawl.pages)} pages ({ok_pages} ok), stopped: {crawl.stopped_reason}"
              + (f", redirected to {crawl.redirected_to}" if crawl.redirected_to else ""))
        for p in crawl.pages:  # which pages were fetched, and why the crawler chose them
            print(f"  {short(p.outcome, 17):<17} d{p.depth} {short(p.url, 70):<70} {getattr(p, 'reason', '') or ''}")

        result = None
        try:
            result = classify_job(db, job.id)
            job.status = JobStatus.REVIEW_REQUIRED if result.needs_review else JobStatus.COMPLETED
            run.status = RunStatus.COMPLETED
        except (NoContentError, AIUnavailableError) as exc:
            db.rollback()
            job.status, job.last_error_code, job.last_error_message = JobStatus.FAILED, exc.code, str(exc)[:500]
            run.status = RunStatus.FAILED
        job.finished_at = run.finished_at = datetime.now(UTC)
        db.commit()

        print(f"\njob status: {job.status}" + (f" ({job.last_error_code}: {job.last_error_message})"
                                               if job.last_error_code else ""))
        rows = db.scalars(select(Classification).where(Classification.job_id == job.id)
                          .options(selectinload(Classification.evidence)).order_by(Classification.id)).all()
        if rows:
            print(f"\n{'CATEGORY':<13} {'STATUS':<10} {'PROV':<5} {'VERIFIED QUOTE (first 80 chars)':<82} SOURCE URL")
            print("-" * 170)
            for c in rows:
                first = c.evidence[0] if c.evidence else None
                flag = " !conflict" if c.conflicts_with_override else ""
                print(f"{c.category:<13} {c.status:<10} {c.provenance:<5} "
                      f"{short(first.quote if first else c.explanation, 82):<82} "
                      f"{short(first.source_url if first else '', 60)}{flag}")
                for extra in c.evidence[1:]:
                    print(f"{'':<30} {short(extra.quote, 82):<82} {short(extra.source_url, 60)}")

        print("\nAI calls:")
        for u in db.scalars(select(AIUsage).where(AIUsage.job_id == job.id).order_by(AIUsage.id)):
            print(f"  #{u.id} {u.provider:<7} {u.model:<24} outcome={u.outcome:<15} error={u.error_code or '-':<18}"
                  f" tokens in/out={u.input_tokens}/{u.output_tokens} latency={u.latency_ms} ms")

        if result:
            print("\nissues:" if result.issues else "\nissues: none")
            for issue in result.issues:
                print(f"  - {issue}")
            cost = "unknown (no prices configured)" if result.est_cost_usd is None else f"${result.est_cost_usd}"
            print(f"provider used: {result.provider} ({result.model}) | tokens in/out (all calls): "
                  f"{result.input_tokens}/{result.output_tokens} | cost: {cost} | needs review: {result.needs_review}")
        print(f"total time: {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
