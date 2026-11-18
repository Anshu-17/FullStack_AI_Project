"""Classify ONE job end to end (plain staged functions, no framework):

  load pages -> select passages -> build prompt -> call AI (retries + fallback)
  -> validate -> add Accounting rule -> check human overrides -> save in ONE transaction

Failure modes (raised, nothing classified is saved):
- NoContentError   (NO_CONTENT):     the crawl produced no usable text. This is a crawl
                                     failure, NOT "not_found" for every category. No AI call.
- AIUnavailableError (AI_UNAVAILABLE): every provider failed after its retries.

Every AI call - successful or not - is recorded in ai_usage (tokens, cost, latency, outcome).
"""
import time
from dataclasses import dataclass, field
from decimal import Decimal
from time import sleep  # imported by name so tests can replace it

from sqlalchemy import select
from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.classifier.prompts import build_messages
from app.classifier.providers import build_structured_model, describe_error, provider_order, provider_settings
from app.classifier.schema import ClassificationOutput
from app.classifier.select import select_passages
from app.classifier.taxonomy import POLICY_VERSION, PROMPT_VERSION, accounting_rule_decision
from app.classifier.validate import CheckedDecision, InvalidModelOutput, validate
from app.config import settings
from app.db.enums import ClassStatus, PageOutcome
from app.db.models import AIUsage, Classification, Evidence, Job, Override, Page
from app.log_config import get_logger

log = get_logger("classifier")

ATTEMPTS_PER_PROVIDER = 3
MAX_WAIT_SECONDS = 10.0  # cap on any wait between attempts, including a provider's Retry-After

# ai_usage.outcome for each error code
OUTCOME_FOR_CODE = {"AI_TIMEOUT": "timeout", "AI_RATE_LIMITED": "rate_limited",
                    "AI_INVALID_OUTPUT": "invalid_output", "AI_AUTH": "error", "AI_ERROR": "error"}


class NoContentError(Exception):
    code = "NO_CONTENT"


class AIUnavailableError(Exception):
    code = "AI_UNAVAILABLE"


class AICallFailed(Exception):
    """One AI call failed. `retryable` says whether trying the same provider again makes sense."""

    def __init__(self, code: str, detail: str, retryable: bool, retry_after: float | None = None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.retryable, self.retry_after = code, detail, retryable, retry_after


@dataclass
class ClassifyResult:
    status_counts: dict[str, int]
    needs_review: bool
    issues: list[str]
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: Decimal | None = None
    latency_ms: int = 0
    conflicts: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ cost

def estimate_cost(input_tokens: int | None, output_tokens: int | None) -> Decimal | None:
    """Cost from the configured prices. None (unknown) when prices are not set - never guessed."""
    if settings.ai_price_input_per_mtok is None or settings.ai_price_output_per_mtok is None:
        return None
    cost = ((input_tokens or 0) * settings.ai_price_input_per_mtok
            + (output_tokens or 0) * settings.ai_price_output_per_mtok) / 1_000_000
    return Decimal(str(round(cost, 6)))


# ------------------------------------------------------------------ one AI call

def _record_usage(db, job_id, provider, model, started, outcome, error_code=None, usage=None) -> AIUsage:
    """Write one ai_usage row and commit it, so it survives even if the job fails later."""
    usage = usage or {}
    row = AIUsage(
        job_id=job_id, provider=provider, model=model,
        input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
        est_cost_usd=estimate_cost(usage.get("input_tokens"), usage.get("output_tokens")) if usage else None,
        latency_ms=int((time.perf_counter() - started) * 1000), outcome=outcome, error_code=error_code,
    )
    db.add(row)
    db.commit()
    return row


def call_once(db, job_id, provider, model, structured_model, messages, passages, pages):
    """One AI call + structural check + validation. Returns (decisions, issues, usage_row).

    Raises AICallFailed (with an error code) on any problem.
    """
    started = time.perf_counter()
    try:
        result = structured_model.invoke(messages)
    except Exception as exc:
        info = describe_error(exc)
        _record_usage(db, job_id, provider, model, started, OUTCOME_FOR_CODE[info.code], info.code)
        log.warning("ai.call_failed", provider=provider, model=model, error_code=info.code, detail=info.detail)
        raise AICallFailed(info.code, info.detail, info.retryable, info.retry_after) from exc

    raw_message = result.get("raw")
    usage = dict(getattr(raw_message, "usage_metadata", None) or {})
    parsed = result.get("parsed")
    try:
        if not isinstance(parsed, ClassificationOutput):
            error = result.get("parsing_error")
            # Keep the END of the message: that is where Pydantic says which field was wrong.
            raise InvalidModelOutput(f"output did not match the schema: {type(error).__name__}: {str(error)[-300:]}")
        decisions, issues = validate(parsed, passages, pages)
    except InvalidModelOutput as exc:
        _record_usage(db, job_id, provider, model, started, "invalid_output", "AI_INVALID_OUTPUT", usage)
        log.warning("ai.invalid_output", provider=provider, model=model, detail=str(exc)[:300])
        raise AICallFailed("AI_INVALID_OUTPUT", str(exc)[:300], retryable=True) from exc

    row = _record_usage(db, job_id, provider, model, started, "ok", None, usage)
    log.info("ai.call_ok", provider=provider, model=model, input_tokens=row.input_tokens,
             output_tokens=row.output_tokens, latency_ms=row.latency_ms)
    return decisions, issues, row


def _wait_seconds(retry_state: RetryCallState) -> float:
    """Exponential backoff with jitter (1s, 2s, ... + random), or the provider's Retry-After; capped."""
    backoff = wait_exponential_jitter(initial=1, max=MAX_WAIT_SECONDS)(retry_state)
    error = retry_state.outcome.exception()
    retry_after = getattr(error, "retry_after", None) or 0
    return min(max(backoff, retry_after), MAX_WAIT_SECONDS)


def call_with_fallback(db, job_id, messages, passages, pages):
    """Try each provider in order; up to 3 attempts each for retryable errors.

    Returns (decisions, issues, provider, model) or raises AIUnavailableError.
    Non-retryable errors (bad key, unknown model) skip straight to the next provider.
    """
    providers = provider_order()
    if not providers:
        raise AIUnavailableError("no AI provider configured (need an API key and a model)")

    errors = []
    for provider in providers:
        _, model = provider_settings(provider)
        structured_model = build_structured_model(provider)
        retrying = Retrying(
            stop=stop_after_attempt(ATTEMPTS_PER_PROVIDER),
            wait=_wait_seconds,
            retry=retry_if_exception(lambda e: isinstance(e, AICallFailed) and e.retryable),
            sleep=lambda seconds: sleep(seconds),
            reraise=True,  # after the last attempt, give us the real error, not tenacity's wrapper
        )
        try:
            decisions, issues, _row = retrying(
                call_once, db, job_id, provider, model, structured_model, messages, passages, pages)
            return decisions, issues, provider, model
        except AICallFailed as exc:
            errors.append(f"{provider}: {exc.code}")
            log.warning("ai.provider_failed", provider=provider, error_code=exc.code)
    raise AIUnavailableError("all AI providers failed: " + ", ".join(errors))


# ------------------------------------------------------------------ overrides

def latest_overrides(db, company_id: int) -> dict[str, str]:
    """Current human answer per category: the highest-version override, unless it was a removal (NULL)."""
    rows = db.scalars(
        select(Override).where(Override.company_id == company_id).order_by(Override.category, Override.version.desc())
    )
    latest: dict[str, str | None] = {}
    for row in rows:
        latest.setdefault(row.category, row.new_status)  # first row per category = highest version
    return {category: status for category, status in latest.items() if status is not None}


# ------------------------------------------------------------------ the job

def classify_job(db, job_id: int) -> ClassifyResult:
    started = time.perf_counter()
    job = db.get(Job, job_id)
    company = job.company
    pages = list(db.scalars(select(Page).where(Page.job_id == job_id)))

    # 1. Nothing readable crawled -> crawl failure, not "not_found" x 6. No AI call.
    if not any(p.outcome == PageOutcome.OK and p.text_content for p in pages):
        raise NoContentError("no page with usable text was crawled")

    # 2. Evidence selection + prompt
    passages = select_passages(pages)
    if not passages:
        raise NoContentError("crawled pages contain no passage long enough to use")
    messages = build_messages(company.name, company.canonical_domain, passages)

    # 3. AI with retries and provider fallback (usage rows are committed as we go)
    decisions, issues, provider, model = call_with_fallback(db, job_id, messages, passages, pages)

    # 4. Accounting by business rule (never by the AI)
    accounting = accounting_rule_decision()
    decisions.append(CheckedDecision(accounting["category"], accounting["status"], accounting["explanation"],
                                     None, provenance=accounting["provenance"]))

    # 5. Compare with active human overrides; the override rows themselves are never changed
    overrides = latest_overrides(db, company.id)
    conflicts = []
    for d in decisions:
        if d.category in overrides and overrides[d.category] != d.status:
            conflicts.append(d.category)
            log.info("classify.conflicts_with_override", company_id=company.id, category=d.category,
                     automated=d.status, override=overrides[d.category])

    # 6. Save 7 classifications + their evidence in ONE transaction
    try:
        for d in decisions:
            is_rule = d.provenance == "rule"
            row = Classification(
                job_id=job_id, company_id=company.id, category=d.category, status=d.status,
                provenance=d.provenance, explanation=d.explanation,
                confidence=None if d.confidence is None else Decimal(str(round(d.confidence, 3))),
                model_provider=None if is_rule else provider, model_name=None if is_rule else model,
                prompt_version=None if is_rule else PROMPT_VERSION, policy_version=POLICY_VERSION,
                conflicts_with_override=d.category in conflicts,
            )
            row.evidence = [Evidence(page_id=e.page_id, source_url=e.source_url, quote=e.quote,
                                     quote_verified=e.quote_verified) for e in d.evidence]
            db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # 7. Summary (tokens/cost over ALL calls for this job, including failed ones)
    usage_rows = list(db.scalars(select(AIUsage).where(AIUsage.job_id == job_id)))
    costs = [u.est_cost_usd for u in usage_rows]
    counts: dict[str, int] = {}
    for d in decisions:
        counts[d.status] = counts.get(d.status, 0) + 1
    result = ClassifyResult(
        status_counts=counts,
        needs_review=bool(issues) or bool(conflicts) or any(d.status == ClassStatus.POSSIBLE for d in decisions),
        issues=issues, provider=provider, model=model,
        input_tokens=sum(u.input_tokens or 0 for u in usage_rows),
        output_tokens=sum(u.output_tokens or 0 for u in usage_rows),
        est_cost_usd=None if any(c is None for c in costs) else sum(costs, Decimal(0)),
        latency_ms=int((time.perf_counter() - started) * 1000),
        conflicts=conflicts,
    )
    log.info("classify.done", job_id=job_id, provider=provider, statuses=counts,
             needs_review=result.needs_review, issues=len(issues))
    return result
