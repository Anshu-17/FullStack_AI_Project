"""App settings, read from environment variables / .env (never hard-code secrets)."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_PRODUCTION_JWT_SECRET_CHARS = 32


class Settings(BaseSettings):
    # env_ignore_empty: "AI_PRICE_INPUT_PER_MTOK=" (blank) means "use the default", not "invalid number".
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # --- General ---
    environment: str = "development"  # development | test | production
    log_level: str = "INFO"
    log_json: bool = True  # JSON logs (False = pretty console logs for local dev)
    cors_origins: str = "http://localhost:8501"  # comma-separated list (Streamlit's port)

    # --- Database ---
    database_url: str = "postgresql+psycopg://postgres:devpass@localhost:5432/bep"

    # --- Auth ---
    jwt_secret: str = "change-me"
    jwt_expires_minutes: int = 480  # a login lasts one working day

    # --- Rate limits (per client IP; slowapi syntax "N/period") ---
    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/minute"     # slows down password guessing
    rate_limit_upload: str = "20/minute"
    rate_limit_default: str = "300/minute"  # everything else

    # --- Demo accounts for `python -m app.db.seed` (blank password = generate one) ---
    seed_reviewer_email: str = "reviewer@demo.local"
    seed_reviewer_password: str = ""
    seed_viewer_email: str = "viewer@demo.local"
    seed_viewer_password: str = ""

    # --- AI providers: google | groq | anthropic | xai | openai ---
    # A provider is only used when BOTH its API key and its model are set.
    ai_provider: str = "google"          # tried first
    ai_fallback_providers: str = "groq"  # comma-separated, tried in order if the primary fails
    ai_timeout_seconds: float = 60
    # Room for the answer AND the model's hidden "thinking" tokens (Gemini 2.5 used ~1,800 of ~3,500 output tokens
    # on real sites), so answers are not cut off. A cut-off answer is treated as invalid output and retried.
    ai_max_output_tokens: int = 8192
    # A provider that says its DAILY quota is used up is skipped by this worker process for this long.
    ai_quota_cooldown_seconds: int = 1800
    google_model: str = "gemini-2.5-flash"
    google_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"  # via Groq's OpenAI-compatible API (120b: stronger than 20b)
    groq_api_key: str = ""
    anthropic_model: str = ""
    anthropic_api_key: str = ""
    xai_model: str = ""
    xai_api_key: str = ""
    openai_model: str = ""
    openai_api_key: str = ""
    # USD per million tokens, for the cost estimate. Unset = cost recorded as unknown (NULL), never guessed.
    ai_price_input_per_mtok: float | None = None
    ai_price_output_per_mtok: float | None = None

    # --- Classification policy ---
    policy_version: str = "v1"
    # p2: quotes must be one continuous span (no "...", no stitching)
    # p3: outdated evidence ("closed in 2015") is "possible", not "not_found"
    prompt_version: str = "p3"

    # --- Crawl limits (section 4.3) ---
    crawl_max_pages: int = 8                # pages per website (homepage + the most relevant links)
    crawl_max_depth: int = 2                # homepage = depth 0
    crawl_timeout_seconds: float = 10.0     # per network operation (connect / read)
    crawl_max_total_bytes: int = 5_000_000  # all pages of one website together
    crawl_max_page_bytes: int = 1_500_000   # one page; bigger -> outcome "too_large"
    crawl_max_redirects: int = 5            # every hop is re-checked by the SSRF guard
    crawl_per_host_concurrency: int = 2     # upper bound; the crawler itself fetches 1 page at a time per site
    crawl_job_deadline_seconds: int = 120   # wall-clock budget for crawling one website
    crawl_user_agent: str = "BusinessEvidenceBot/0.1 (research prototype)"
    # Comma-separated hostnames allowed to resolve to private IPs (local test fixtures ONLY).
    # "*.fixture.test" allows every subdomain of fixture.test. Ignored when ENVIRONMENT=production.
    crawl_allowed_private_hosts: str = ""
    # TEST-ONLY: "127.0.0.1:8765" sends requests for *.fixture.test hosts to the local fixture server
    # (fixtures/server.py) instead of DNS. Empty = off. Ignored when ENVIRONMENT=production.
    crawl_fixture_server: str = ""

    # --- Worker (section 4.5) ---
    worker_concurrency: int = 2   # jobs processed in parallel by one worker process (free-tier AI limits)
    job_lease_seconds: int = 120  # a job whose lease is not renewed for this long is presumed abandoned
    job_max_attempts: int = 3
    job_backoff_base_seconds: int = 10  # retry waits: base * 2^(attempt-1), max 300 s (shorter only for tests)

    @model_validator(mode="after")
    def normalise_database_url(self):
        """Accept the connection string exactly as Supabase / Render show it.

        - "postgres://" or "postgresql://" -> "postgresql+psycopg://" (tells SQLAlchemy to use psycopg 3)
        - a Supabase host without sslmode gets "sslmode=require" (Supabase only accepts encrypted connections)
        """
        url = self.database_url.strip()
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url[len(prefix):]
        if ("supabase.co" in url or "supabase.com" in url) and "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        self.database_url = url
        return self

    @model_validator(mode="after")
    def production_worker_defaults(self):
        """Free hosting has little memory and free AI tiers have tight limits: 1 worker thread in production,
        unless WORKER_CONCURRENCY is set explicitly."""
        if self.environment == "production" and "worker_concurrency" not in self.model_fields_set:
            self.worker_concurrency = 1
        return self

    @model_validator(mode="after")
    def refuse_weak_secret_in_production(self):
        """In production, a missing / default / short JWT secret would let anyone forge logins: refuse to start."""
        if self.environment == "production" and (
            not self.jwt_secret or self.jwt_secret == "change-me"
            or len(self.jwt_secret) < MIN_PRODUCTION_JWT_SECRET_CHARS
        ):
            raise ValueError(
                f"JWT_SECRET must be set to a random string of at least {MIN_PRODUCTION_JWT_SECRET_CHARS} characters "
                "when ENVIRONMENT=production. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
