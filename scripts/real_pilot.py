"""Real-site pilot: upload sample-data/real_companies.csv through the API, run ONE run, report from the database.

Needs the API and ONE worker running WITHOUT any test-only settings (real crawling, real AI). In backend/:

    REVIEWER_PW=... python ../scripts/real_pilot.py <out.md>            # upload + run + report
    python ../scripts/real_pilot.py <out.md> <run_id>                   # report only

The report lists, per company: job status, pages ok / not ok, the homepage redirect (if any), the 7 answers and
error codes; then totals, AI calls and tokens, and every yes/possible quote for a MANUAL evidence audit.
Sites that block us or fail are reported as they are - no extra retries beyond the normal policy.
"""
import csv
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.models import AIUsage, Classification, Job, Page, Run  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

CSV_PATH = BACKEND.parent / "sample-data" / "real_companies.csv"
CATS = ["accounting", "agronomy", "grain", "energy", "feed", "gas_station", "retail_store"]
SHORT = {"yes": "Y", "possible": "P", "not_found": "-", None: "?"}


def main(out: Path, report_run_id: int | None = None) -> None:
    if report_run_id is not None:  # report only (e.g. after a manual retry of failed jobs)
        return report(out, report_run_id, upload_note="see the first report of this run")
    client = httpx.Client(base_url=os.environ.get("API_URL", "http://localhost:8000"), timeout=60)
    token = client.post("/api/auth/login", json={"email": "reviewer@demo.local",
                                                 "password": os.environ["REVIEWER_PW"]}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    data = CSV_PATH.read_bytes()
    up = client.post("/api/uploads", headers=h, files={"file": (CSV_PATH.name, data, "text/csv")}).json()
    print("upload:", up["upload_id"], up["counts"], [(r["row_no"], r["result"], r["message"]) for r in up["rows"]])
    ids = [r["company_id"] for r in client.get(f"/api/uploads/{up['upload_id']}/rows", headers=h,
                                               params={"page_size": 50}).json()["items"]]
    run = client.post("/api/runs", headers={**h, "Idempotency-Key": f"real-pilot-{int(time.time())}"},
                      json={"company_ids": ids}).json()
    run_id = run["run_id"]
    print(f"run {run_id}: {run['total_items']} jobs, skipped {run['skipped']}")
    while True:
        r = client.get(f"/api/runs/{run_id}", headers=h).json()
        print(f"  {datetime.now(UTC):%H:%M:%S}Z {r['status']:<22} {r['progress']['done']}/{r['progress']['total']} "
              f"{ {k: v for k, v in r['counts'].items() if v} }")
        if r["status"] in ("completed", "completed_with_errors", "failed", "cancelled"):
            break
        time.sleep(10)
    report(out, run_id, upload_note=f"upload #{up['upload_id']} ({up['counts']})")


def report(out: Path, run_id: int, upload_note: str) -> None:
    sources = {row["website"].split("//")[1].removeprefix("www.").lower(): row
               for row in csv.DictReader(open(CSV_PATH, encoding="utf-8"))}
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        jobs = db.scalars(select(Job).where(Job.run_id == run_id).order_by(Job.id)).all()
        rows, audit = [], []
        for job in jobs:
            pages = db.scalars(select(Page).where(Page.job_id == job.id).order_by(Page.depth, Page.id)).all()
            ok = sum(p.outcome == "ok" for p in pages)
            outcomes = {}
            for p in pages:
                if p.outcome != "ok":
                    outcomes[p.outcome] = outcomes.get(p.outcome, 0) + 1
            home = pages[0] if pages else None
            redirect = ""
            if home and home.final_url and urlsplit(home.final_url).netloc != urlsplit(home.url).netloc:
                redirect = home.final_url
            cls = {c.category: c for c in db.scalars(select(Classification).where(Classification.job_id == job.id)
                                                     .options(selectinload(Classification.evidence)))}
            statuses = " ".join(f"{SHORT[cls[c].status] if c in cls else '?'}" for c in CATS)
            provider = next((f"{c.model_provider}" for c in cls.values() if c.model_provider), "")
            rows.append((job.company.name, job.company.canonical_domain, job.status, job.attempt_count,
                         f"{ok}/{len(pages)}", outcomes, redirect, statuses, job.last_error_code or "", provider))
            for c in cls.values():
                if c.status in ("yes", "possible") and c.provenance == "site":
                    for e in c.evidence or [None]:
                        audit.append((job.company.canonical_domain, c.category, c.status,
                                      e.quote if e else "(no quote)", e.source_url if e else ""))
        ai = db.execute(select(AIUsage.provider, AIUsage.model, AIUsage.outcome, func.count(),
                               func.coalesce(func.sum(AIUsage.input_tokens), 0),
                               func.coalesce(func.sum(AIUsage.output_tokens), 0))
                        .join(Job, Job.id == AIUsage.job_id).where(Job.run_id == run_id)
                        .group_by(AIUsage.provider, AIUsage.model, AIUsage.outcome)).all()
        by_status: dict[str, int] = {}
        for job in jobs:
            by_status[job.status] = by_status.get(job.status, 0) + 1
        total_s = (run.finished_at - run.created_at).total_seconds()

    lines = [
        "## Run data (generated from the database by `scripts/real_pilot.py`)",
        "",
        f"- Date: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC; {upload_note}; run #{run_id}",
        f"- Machine: {platform.platform()}, Python {platform.python_version()}, PostgreSQL 18; one worker process (no test hooks; "
        f"threads: see the run notes); prompt `{settings.prompt_version}`, "
        f"policy `{settings.policy_version}`; AI order: {settings.ai_provider} then {settings.ai_fallback_providers}",
        f"- Total time (run created -> finished): {total_s:.0f} s; jobs by status: {by_status}",
        "- AI calls: " + "; ".join(f"`{p}/{m}` {o}: {n} (tokens in/out {ti}/{to})" for p, m, o, n, ti, to in ai),
        "",
        "Answers: Y = yes, P = possible, - = not_found, ? = no answer (job failed). Order: "
        "Acct Agro Grain Energy Feed Gas Retail (Accounting = business rule).",
        "",
        "| company | domain | job | attempts | pages ok | other page outcomes | homepage redirected to | answers | error | AI |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, domain, status, att, ok, outc, redir, st, err, prov in rows:
        lines.append(f"| {name} | {domain} | {status} | {att} | {ok} | {outc or ''} | {redir} | `{st}` | {err} | "
                     f"{prov} |")
    lines += ["", "### Website sources", "", "| domain | where the website address came from |", "|---|---|"]
    for domain, row in sources.items():
        lines.append(f"| {domain} | {row['source']} |")
    lines += ["", "### Evidence audit list (every site-derived yes / possible quote)", "",
              "| domain | category | status | quote | source page | judgement |", "|---|---|---|---|---|---|"]
    for domain, cat, status, quote, url in audit:
        q = " ".join(quote.split()).replace("|", "\\|")
        lines.append(f"| {domain} | {cat} | {status} | \"{q[:220]}\" | {url.split('//')[-1][:70]} | TODO |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else None)  # optional: run id = report only
