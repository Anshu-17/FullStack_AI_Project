"""Quality evaluation on the LABELLED fixture websites, with the REAL pipeline and REAL AI.

    (fixture server running:  python fixtures/server.py)
    cd backend
    CRAWL_FIXTURE_SERVER=127.0.0.1:8765 CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test \
        python ../scripts/evaluate.py ../docs/evidence/quality_evaluation.md

What it does:
1. reads sample-data/labelled_fixtures.csv (expected answer per category, written from the brief's rules)
2. adds the sites that should be classified as companies with source='fixture' (test data)
3. starts ONE run and processes it with the normal worker code (crawl -> AI -> validation -> save)
4. compares the AUTOMATED answers with the labels: precision / recall per category (positive = "yes"),
   a confusion table, the exact-match rate, and a list of every yes/possible quote for a manual audit.

This is a SMALL SYNTHETIC set (hand-written fixture pages): it checks that the rules are applied, it is
not a measure of accuracy on real websites.
"""
import csv
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.classifier.taxonomy import POLICY_VERSION, PROMPT_VERSION, SITE_CATEGORY_NAMES  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.models import AIUsage, Classification, Company, Job, Run  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.ingest import ingest_rows  # noqa: E402
from app.services.runs import create_run  # noqa: E402
from app.worker.leases import claim_next_job, recover_expired_leases  # noqa: E402
from app.worker.process import process_job  # noqa: E402

LABELS = BACKEND.parent / "sample-data" / "labelled_fixtures.csv"
STATUSES = ("yes", "possible", "not_found")
WORKER_ID = "evaluate-script"


def load_labels() -> list[dict]:
    with open(LABELS, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["expected_job"] == "classified"]


def run_pipeline(labels: list[dict]) -> int:
    """Create the fixture companies + one run, and process it to the end. Returns the run id."""
    with SessionLocal() as db:
        rows = [{"row_no": i + 1, "name": r["company_name"], "website": r["website"]} for i, r in enumerate(labels)]
        upload = ingest_rows(db, rows, file_name="labelled_fixtures.csv", source="fixture")
        ids = [r.company_id for r in upload.rows]
        run, _, skipped = create_run(db, ids, idempotency_key=f"evaluate-{int(time.time())}", source="evaluation")
        run_id = run.id
        if skipped:
            print("skipped (already in progress):", skipped)
    print(f"run {run_id}: {len(ids)} fixture companies")

    while True:  # the same loop the worker runs, but only until this run is finished
        with SessionLocal() as db:
            recover_expired_leases(db)
            status = db.get(Run, run_id).status
            if status not in ("queued", "running"):
                return run_id
            job_id = claim_next_job(db, WORKER_ID)
        if job_id is None:
            time.sleep(2)  # e.g. a job waiting for its retry time
            continue
        process_job(job_id, WORKER_ID)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            print(f"  job {job_id} {job.company.canonical_domain}: {job.status} {job.last_error_code or ''}")


def pct(n, d) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a (0/0)"


def evaluate(run_id: int, labels: list[dict]) -> str:
    expected = {r["website"].split("//")[1].rstrip("/"): r for r in labels}
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        jobs = db.scalars(select(Job).where(Job.run_id == run_id).order_by(Job.id)).all()
        predicted, quotes, job_info = {}, [], {}
        for job in jobs:
            domain = job.company.canonical_domain
            job_info[domain] = (job.status, job.last_error_code, job.company.name)
            for c in db.scalars(select(Classification).where(Classification.job_id == job.id)
                                .options(selectinload(Classification.evidence))):
                if c.category == "accounting":
                    continue  # business rule, not evaluated
                predicted[(domain, c.category)] = c.status
                if c.status in ("yes", "possible"):
                    for e in c.evidence or [None]:
                        quotes.append((domain, c.category, c.status, e.quote if e else "(no quote)",
                                       e.source_url if e else "", c.model_provider, c.explanation))
        models = db.execute(select(Classification.model_provider, Classification.model_name, func.count())
                            .join(Job, Job.id == Classification.job_id)
                            .where(Job.run_id == run_id, Classification.model_provider.is_not(None))
                            .group_by(Classification.model_provider, Classification.model_name)).all()
        usage = db.execute(select(AIUsage.provider, AIUsage.outcome, func.count(),
                                  func.coalesce(func.sum(AIUsage.input_tokens), 0),
                                  func.coalesce(func.sum(AIUsage.output_tokens), 0))
                           .join(Job, Job.id == AIUsage.job_id).where(Job.run_id == run_id)
                           .group_by(AIUsage.provider, AIUsage.outcome)).all()
        started, finished = run.started_at, run.finished_at

    lines = [
        "# Quality evaluation - labelled fixture websites (SMALL SYNTHETIC SET)",
        "",
        "> **Synthetic data.** Hand-written fixture pages served locally (`fixtures/sites/`), labelled from the "
        "brief's rules (`sample-data/labelled_fixtures.csv`). This checks that the rules are applied; it is NOT "
        "an accuracy measure on real websites. Sample: "
        f"{len(expected)} sites x 6 site categories = {len(expected) * 6} answers.",
        "",
        f"- Date: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC; run #{run_id} "
        f"({(finished - started).total_seconds():.0f} s)" if started and finished else f"- Run #{run_id}",
        f"- Pipeline: real crawl (local fixture server) -> real AI -> validation; prompt `{PROMPT_VERSION}`, "
        f"policy `{POLICY_VERSION}`; AI order: {settings.ai_provider} then {settings.ai_fallback_providers or '-'}",
        "- Models that produced the answers: " + ", ".join(f"`{p}/{m}` ({n} answers)" for p, m, n in models),
        "- AI calls: " + "; ".join(f"{p} {o}: {n} (tokens in/out {ti}/{to})" for p, o, n, ti, to in usage),
        "- Accounting is a business rule (always yes) and is not evaluated. Positive class = `yes`.",
        "",
        "## Jobs",
        "",
        "| site | job status | error |",
        "|---|---|---|",
    ]
    lines += [f"| {d} | {s} | {e or ''} |" for d, (s, e, _) in job_info.items()]

    lines += ["", "## Precision / recall per category (positive = yes)", "",
              "| category | precision | recall | exact match |", "|---|---|---|---|"]
    total_match = total = 0
    confusion_rows = []
    for cat in SITE_CATEGORY_NAMES:
        tp = fp = fn = match = n = 0
        conf = {(e, p): 0 for e in STATUSES for p in (*STATUSES, "missing")}
        for domain, label in expected.items():
            exp, pred = label[cat], predicted.get((domain, cat), "missing")
            conf[(exp, pred)] += 1
            n += 1
            match += exp == pred
            tp += exp == "yes" and pred == "yes"
            fp += exp != "yes" and pred == "yes"
            fn += exp == "yes" and pred != "yes"
        total_match, total = total_match + match, total + n
        lines.append(f"| {cat} | {pct(tp, tp + fp)} | {pct(tp, tp + fn)} | {pct(match, n)} |")
        confusion_rows.append((cat, conf))
    lines += ["", f"**Overall exact match (expected status == predicted status): {pct(total_match, total)}**", ""]

    lines += ["## Confusion tables (rows = expected, columns = predicted)", ""]
    for cat, conf in confusion_rows:
        lines += [f"**{cat}**", "", "| expected \\ predicted | yes | possible | not_found | missing |", "|---|---|---|---|---|"]
        for e in STATUSES:
            lines.append(f"| {e} | " + " | ".join(str(conf[(e, p)]) for p in (*STATUSES, "missing")) + " |")
        lines.append("")

    lines += ["## Per site: expected vs predicted", "", "| site | " + " | ".join(SITE_CATEGORY_NAMES) + " |",
              "|---|" + "---|" * len(SITE_CATEGORY_NAMES)]
    for domain, label in expected.items():
        cells = []
        for cat in SITE_CATEGORY_NAMES:
            exp, pred = label[cat], predicted.get((domain, cat), "missing")
            cells.append(pred if exp == pred else f"**{pred}** (expected {exp})")
        lines.append(f"| {domain.split('.')[0]} | " + " | ".join(cells) + " |")

    lines += ["", "## Evidence audit: every yes / possible with its verified quote", "",
              "Judgement column: filled in by hand after reading the quote (OK = the quote supports the answer).", "",
              "| site | category | status | quote | source | judgement |", "|---|---|---|---|---|---|"]
    for domain, cat, status, quote, url, _provider, _expl in quotes:
        q = " ".join(quote.split()).replace("|", "\\|")
        lines.append(f"| {domain.split('.')[0]} | {cat} | {status} | \"{q}\" | {url.split('//')[-1]} | TODO |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    labels = load_labels()
    run_id = run_pipeline(labels)
    report = evaluate(run_id, labels)
    if out:
        out.write_text(report, encoding="utf-8", newline="\n")
        print(f"written {out}")
    else:
        print(report)
