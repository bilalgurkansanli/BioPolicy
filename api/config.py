"""Application configuration.

Loaded once at import time from the environment (and `.env` locally). Two rules
govern this module:

1. **Fail loudly, and early.** A missing key must surface as a startup error
   naming the key, not as a 500 three layers deep inside a provider call an hour
   later.

2. **Fail loudly *where it matters*.** In `preview` and `production` every
   credential is mandatory and a missing one aborts boot. In `development` they
   may be absent so that scaffolding, unit tests and `--help` work on a laptop
   with no accounts attached; `/api/health` then reports precisely which
   providers are unconfigured. This is a deliberate asymmetry, not laziness —
   see docs/adr/001.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "preview", "production"]

# Credentials without which the service cannot do its job. Checked as a group so
# the operator sees every missing key at once instead of fixing them one boot at
# a time.
_REQUIRED_IN_DEPLOYED_ENVS: tuple[str, ...] = (
    "supabase_url",
    "supabase_service_role_key",
    "supabase_anon_key",
    "database_url",
    "anthropic_api_key",
    "google_api_key",
    "purge_job_secret",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- runtime -------------------------------------------------------------
    app_env: AppEnv = "development"
    log_level: str = "INFO"

    # --- Supabase ------------------------------------------------------------
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_anon_key: str | None = None
    database_url: str | None = None
    supabase_storage_bucket: str = "documents"

    # --- Anthropic -----------------------------------------------------------
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # --- Google --------------------------------------------------------------
    google_api_key: str | None = None
    gemini_embedding_model: str = "gemini-embedding-001"
    # WHY these have no default: the spec forbids fabricating model IDs. They are
    # filled in from a verified live model list at build time (docs/adr/004).
    # Empty means "this capability is unavailable", and health reports it.
    gemini_fallback_model: str = ""
    gemini_ocr_model: str = ""

    # --- budget & quotas -----------------------------------------------------
    global_budget_usd: float = 30.0
    user_daily_message_limit: int = 40
    user_daily_document_limit: int = 5

    # --- ingestion limits ----------------------------------------------------
    max_upload_bytes: int = 25 * 1024 * 1024
    max_page_count: int = 250
    max_ocr_page_count: int = 30

    # --- retention -----------------------------------------------------------
    retention_hours: int = 24
    purge_job_secret: str | None = None

    # --- anti-hallucination toggles -----------------------------------------
    # The eval harness flips these to produce the with/without ablation table.
    # They are configuration, not feature flags to be left half-on in prod.
    enable_citation_binding: bool = True
    enable_self_verification: bool = True
    enable_query_rewrite: bool = True
    enable_rerank: bool = False

    # --- CORS ----------------------------------------------------------------
    # The browser talks to the API same-origin through a Next.js rewrite, so this
    # is normally empty. Populated only for local split-origin development.
    cors_allow_origins: list[str] = Field(default_factory=list)

    # -------------------------------------------------------------------------
    @property
    def is_deployed(self) -> bool:
        return self.app_env in ("preview", "production")

    @property
    def retention_interval_sql(self) -> str:
        return f"{self.retention_hours} hours"

    def missing_credentials(self) -> list[str]:
        """Required credentials that are absent. Empty means fully configured."""
        return [name for name in _REQUIRED_IN_DEPLOYED_ENVS if not getattr(self, name)]

    @model_validator(mode="after")
    def _enforce_credentials_when_deployed(self) -> Settings:
        if self.is_deployed:
            missing = self.missing_credentials()
            if missing:
                raise ValueError(
                    f"APP_ENV={self.app_env} requires these environment variables, "
                    f"which are missing or empty: {', '.join(m.upper() for m in missing)}. "
                    "See .env.example. Refusing to start — a half-configured deployment "
                    "fails in ways that look like bugs."
                )
        return self

    @model_validator(mode="after")
    def _sanity_check_limits(self) -> Settings:
        if self.max_ocr_page_count > self.max_page_count:
            raise ValueError(
                "MAX_OCR_PAGE_COUNT must not exceed MAX_PAGE_COUNT; vision OCR is the "
                "single most expensive operation in the pipeline and its cap must bind."
            )
        if self.global_budget_usd <= 0:
            raise ValueError("GLOBAL_BUDGET_USD must be positive.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Use this everywhere; do not instantiate Settings."""
    return Settings()
