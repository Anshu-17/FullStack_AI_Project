"""Small helpers to create test rows (work with any session)."""
from app.db.models import Company, Job, PolicyVersion, Run


def ensure_policy(db, version="v1"):
    if db.get(PolicyVersion, version) is None:
        db.add(PolicyVersion(version=version, description="test policy", rules={}, is_active=True))
        db.flush()


def make_company(db, n: int = 1, name: str | None = None) -> Company:
    company = Company(name=name or f"Co-op {n}", website_url=f"https://coop{n}.example/",
                      canonical_domain=f"coop{n}.example")
    db.add(company)
    db.flush()
    return company


def make_run(db, companies: list[Company], statuses: list[str] | None = None, **job_fields) -> tuple[Run, list[Job]]:
    ensure_policy(db)
    run = Run(policy_version="v1", total_items=len(companies))
    db.add(run)
    db.flush()
    jobs = []
    for i, company in enumerate(companies):
        job = Job(run_id=run.id, company_id=company.id, status=(statuses[i] if statuses else "queued"), **job_fields)
        db.add(job)
        jobs.append(job)
    db.flush()
    return run, jobs
