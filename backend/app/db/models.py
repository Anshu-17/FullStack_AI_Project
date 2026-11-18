"""Database tables (SQLAlchemy 2.x).

Lifecycle:  upload -> company -> run -> job -> attempts -> pages
            -> classifications -> evidence -> human overrides

Key integrity rules are enforced by the database itself (unique constraints,
foreign keys, CHECKs), not only by application code, so they hold even with
concurrent requests or a crashed worker.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.enums import (
    AttemptStatus,
    Category,
    ClassStatus,
    CompanySource,
    JobStatus,
    PageOutcome,
    Provenance,
    Role,
    RunStatus,
    UploadRowResult,
    values,
)

# Predictable constraint names, so migrations can find and drop them later.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def one_of(column: str, enum_cls) -> str:
    """CHECK constraint text: column must be one of the enum's values."""
    allowed = ", ".join(f"'{v}'" for v in values(enum_cls))
    return f"{column} IN ({allowed})"


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------- users


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(one_of("role", Role), name="role"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------- companies & intake


class Company(Base):
    """One real business, identified by its cleaned website domain."""

    __tablename__ = "companies"
    __table_args__ = (CheckConstraint(one_of("source", CompanySource), name="source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # user = real company; fixture / synthetic = TEST DATA (shown with a "Test data" badge, can be hidden)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=CompanySource.USER,
                                        server_default=CompanySource.USER.value)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)  # normalized start URL
    # e.g. "agtegra.com" - UNIQUE: the same business can never be stored twice (scenario C)
    canonical_domain: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Upload(Base):
    """One CSV file (or single-URL submission) and its validation summary."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    file_name: Mapped[str | None] = mapped_column(String(300))
    file_sha256: Mapped[str | None] = mapped_column(String(64))  # spot re-uploads of the same file
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    existing_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_col()

    rows: Mapped[list["UploadRow"]] = relationship(back_populates="upload", cascade="all, delete-orphan")


class UploadRow(Base):
    """Row-level result for an upload: what was sent and what happened to it."""

    __tablename__ = "upload_rows"
    __table_args__ = (
        UniqueConstraint("upload_id", "row_no"),
        CheckConstraint(one_of("result", UploadRowResult), name="result"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = first data row
    raw_name: Mapped[str | None] = mapped_column(Text)
    raw_url: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))

    upload: Mapped[Upload] = relationship(back_populates="rows")


# ---------------------------------------------------------------- policy


class PolicyVersion(Base):
    """Taxonomy + business rules in force (e.g. 'Accounting = Yes by rule')."""

    __tablename__ = "policy_versions"

    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------- work: runs, jobs, attempts


class Run(Base):
    """A batch of companies to research."""

    __tablename__ = "runs"
    __table_args__ = (CheckConstraint(one_of("status", RunStatus), name="status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=RunStatus.QUEUED)
    # Same key sent twice -> same run returned, no duplicate (scenario C)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    policy_version: Mapped[str] = mapped_column(ForeignKey("policy_versions.version"), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # crawl limits, model, ...
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_col()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    jobs: Mapped[list["Job"]] = relationship(back_populates="run")


class Job(Base):
    """One company inside one run (a 'run item'). This is the worker's to-do list."""

    __tablename__ = "jobs"
    __table_args__ = (
        # One job per company per run: no double-processing (scenarios A, C)
        UniqueConstraint("run_id", "company_id"),
        CheckConstraint(one_of("status", JobStatus), name="status"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        # Fast lookup of claimable work: queued jobs whose retry time has come
        Index("ix_jobs_claimable", "status", "next_attempt_at"),
        # Fast lookup of expired leases (crash recovery)
        Index("ix_jobs_lease", "lease_expires_at", postgresql_where=text("status = 'running'")),
        # At most ONE active (queued/running) job per company across all runs: two runs started at the
        # same moment cannot both research the same company (scenario C), enforced by the database.
        Index("uq_jobs_one_active_per_company", "company_id", unique=True,
              postgresql_where=text("status IN ('queued', 'running')")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=JobStatus.QUEUED)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )  # backoff: not claimable before this time
    # Lease: "worker X owns this job until time T". Expired lease = worker presumed dead.
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(50))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[Run] = relationship(back_populates="jobs")
    company: Mapped[Company] = relationship()


class Attempt(Base):
    """Every try at a job, successful or not (retry history, scenario B)."""

    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_no"),
        CheckConstraint(one_of("status", AttemptStatus), name="status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AttemptStatus.RUNNING)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    """Status-change diary for a job (observability and debugging)."""

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------- findings: pages, decisions, evidence


class Page(Base):
    """A page the crawler tried to fetch, and what happened."""

    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("job_id", "url"),
        CheckConstraint(one_of("outcome", PageOutcome), name="outcome"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)        # URL we asked for
    final_url: Mapped[str | None] = mapped_column(String(2048))          # after redirects
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    text_content: Mapped[str | None] = mapped_column(Text)  # cleaned visible text, size-capped
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = created_at_col()


class Classification(Base):
    """An automated decision for one category in one job (rule- or site-derived)."""

    __tablename__ = "classifications"
    __table_args__ = (
        # One answer per category per job: no duplicate finalized outcomes (scenario A)
        UniqueConstraint("job_id", "category"),
        CheckConstraint(one_of("category", Category), name="category"),
        CheckConstraint(one_of("status", ClassStatus), name="status"),
        CheckConstraint(one_of("provenance", Provenance), name="provenance"),
        Index("ix_classifications_company_category", "company_id", "category"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provenance: Mapped[str] = mapped_column(String(10), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # Model's self-reported confidence. NOT a calibrated probability (section 2.2).
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    model_provider: Mapped[str | None] = mapped_column(String(50))  # null for rule-based
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(ForeignKey("policy_versions.version"), nullable=False)
    # True when this scan disagrees with an active human override (scenario E)
    conflicts_with_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_col()

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="classification", cascade="all, delete-orphan")


class Evidence(Base):
    """The exact quote and source URL supporting a classification."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    classification_id: Mapped[int] = mapped_column(
        ForeignKey("classifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)  # short excerpt, not a full page copy
    # True when our validator found this exact quote in the stored page text
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_col()

    classification: Mapped[Classification] = relationship(back_populates="evidence")


# ---------------------------------------------------------------- human review


class Override(Base):
    """A reviewer's correction. Append-only history: rows are never updated or deleted.

    The current human answer for (company, category) is the row with the highest
    version. `version` is unique per (company, category): two reviewers saving
    against the same expected version cannot both win (optimistic locking, scenario G).
    """

    __tablename__ = "overrides"
    __table_args__ = (
        UniqueConstraint("company_id", "category", "version"),
        CheckConstraint(one_of("category", Category), name="category"),
        CheckConstraint("new_status IS NULL OR " + one_of("new_status", ClassStatus), name="new_status"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20))  # what was shown before the change
    # New human answer. NULL = override removed (go back to the automated answer).
    new_status: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_classification_id: Mapped[int | None] = mapped_column(ForeignKey("classifications.id"))
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------- AI cost tracking


class AIUsage(Base):
    """One AI call: tokens, estimated cost, latency, outcome (section 4.6 metrics)."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    est_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))  # estimate from a price table
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # ok | timeout | rate_limited | invalid_output | error
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = created_at_col()
