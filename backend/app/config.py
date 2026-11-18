"""App settings, read from environment variables / .env (never hard-code secrets)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- General ---
    environment: str = "development"  # development | test | production
    log_level: str = "INFO"
    log_json: bool = True  # JSON logs (False = pretty console logs for local dev)
    cors_origins: str = "http://localhost:5173"  # comma-separated list

    # --- Database ---
    database_url: str = "postgresql+psycopg://postgres:devpass@localhost:5432/bep"

    # --- Auth ---
    jwt_secret: str = "change-me"
    jwt_expires_minutes: int = 480

    # --- Demo accounts for `python -m app.db.seed` (blank password = generate one) ---
    seed_reviewer_email: str = "reviewer@demo.local"
    seed_reviewer_password: str = ""
    seed_viewer_email: str = "viewer@demo.local"
    seed_viewer_password: str = ""

    # --- AI providers (leave blank the ones you don't use) ---
    ai_provider: str = "anthropic"  # anthropic | google | xai
    ai_fallback_providers: str = ""  # e.g. "google,xai"
    ai_model: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    xai_api_key: str = ""

    # --- Classification policy ---
    policy_version: str = "v1"
    prompt_version: str = "p1"

    # --- Crawl limits (section 4.3) ---
    crawl_max_pages: int = 15
    crawl_max_depth: int = 2
    crawl_timeout_seconds: float = 10.0
    crawl_max_total_bytes: int = 5_000_000
    crawl_per_host_concurrency: int = 2
    crawl_job_deadline_seconds: int = 120

    # --- Worker (section 4.5) ---
    worker_concurrency: int = 4
    job_lease_seconds: int = 120
    job_max_attempts: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
