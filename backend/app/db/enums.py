"""Allowed values for status/category columns.

Stored as plain strings in the database with CHECK constraints (simpler to
migrate than Postgres ENUM types). The frontend turns codes into labels.
"""
from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"      # read + export
    REVIEWER = "reviewer"  # also upload, run, correct


class Category(StrEnum):
    ACCOUNTING = "accounting"
    AGRONOMY = "agronomy"
    GRAIN = "grain"
    ENERGY = "energy"
    FEED = "feed"
    GAS_STATION = "gas_station"
    RETAIL_STORE = "retail_store"


class ClassStatus(StrEnum):
    YES = "yes"
    POSSIBLE = "possible"
    NOT_FOUND = "not_found"


class Provenance(StrEnum):
    SITE = "site"  # derived from website evidence
    RULE = "rule"  # set by an explicit business rule (e.g. Accounting)


class UploadRowResult(StrEnum):
    ACCEPTED = "accepted"    # new company created
    EXISTING = "existing"    # valid, company already in the database (linked, not duplicated)
    DUPLICATE = "duplicate"  # same website appears earlier in the same file
    INVALID = "invalid"      # failed validation


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"                        # cancel requested, in-flight items finishing
    COMPLETED = "completed"                          # every item completed
    COMPLETED_WITH_ERRORS = "completed_with_errors"  # partial success
    FAILED = "failed"                                # no item succeeded
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    REVIEW_REQUIRED = "review_required"  # finished, but has Possible answers or conflicts
    FAILED = "failed"                    # retries exhausted or permanent error
    CANCELLED = "cancelled"


JOB_TERMINAL = {JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED, JobStatus.FAILED, JobStatus.CANCELLED}


class AttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"  # worker died; lease expired and the job was re-queued


class PageOutcome(StrEnum):
    OK = "ok"
    HTTP_ERROR = "http_error"          # 4xx / 5xx
    TIMEOUT = "timeout"
    BLOCKED_UNSAFE = "blocked_unsafe"  # SSRF protection (private IP, bad scheme, ...)
    ROBOTS_DISALLOWED = "robots_disallowed"
    TOO_LARGE = "too_large"
    NOT_HTML = "not_html"
    EMPTY = "empty"
    ERROR = "error"                    # anything else (DNS failure, broken HTML, ...)


def values(enum_cls) -> list[str]:
    return [e.value for e in enum_cls]
