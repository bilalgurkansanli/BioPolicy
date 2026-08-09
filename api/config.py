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
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    # Deliberately small. Every question is a real model call against a real
    # bill, and this is a portfolio demo rather than a service.
    user_daily_message_limit: int = 3
    user_daily_document_limit: int = 1

    # Accounts exempt from the two limits above, by email address. Empty by
    # default, so a deployment that forgets to set it grants nothing.
    #
    # The address is only ever *matched* here — it is read back out of
    # `auth.users` at check time, never taken from a token (see api/accounts.py).
    # It lives in the environment rather than in code because it is a personal
    # address and this repository is public.
    unlimited_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Provider rates the breaker cannot infer for itself. Anthropic's are
    # verified in `api/pricing.py`; Google's arrive here, because ADR 004's rule
    # against fabricating a model id applies to its price as well.
    #
    #   MODEL_PRICES=gemini-embedding-001:0.15:0,gemini-3.6-flash:1.50:7.50
    #
    # `model:input:output` in USD per million tokens. An unlisted model is not
    # free — it raises, and the call is recorded as unpriced.
    model_prices: Annotated[dict[str, tuple[float, float]], NoDecode] = Field(default_factory=dict)
    # Required alongside a price, never defaulted to today. A date the operator
    # did not type is a date nobody checked.
    model_prices_verified_on: str = ""

    @field_validator("model_prices", mode="before")
    @classmethod
    def _parse_model_prices(cls, value: object) -> object:
        """Parse `model:in:out,model:in:out` into a mapping.

        Every failure mode here is a typo in a deployment variable, so each one
        names the offending entry rather than the field. A price parsed wrongly
        is worse than one absent: absent raises, wrong quietly under-counts.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return {}
        if stripped.startswith("{"):
            return stripped  # a JSON object; let the normal parser have it

        prices: dict[str, tuple[float, float]] = {}
        for entry in stripped.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) != 3:
                raise ValueError(
                    f"MODEL_PRICES entry {entry!r} is not `model:input:output` — "
                    "three colon-separated fields, prices in USD per million tokens."
                )
            model, raw_input, raw_output = (part.strip() for part in parts)
            if not model:
                raise ValueError(f"MODEL_PRICES entry {entry!r} has no model id.")
            try:
                prices[model] = (float(raw_input), float(raw_output))
            except ValueError:
                raise ValueError(
                    f"MODEL_PRICES entry {entry!r} has a price that is not a number."
                ) from None
        return prices

    @field_validator("unlimited_emails", "cors_allow_origins", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        """Accept `a@b.com,c@d.com` as well as a JSON array.

        pydantic-settings parses a `list[str]` from the environment as JSON,
        which means an operator following the obvious comma convention gets a
        stack trace at boot rather than a setting. For an allowlist that is a
        bad failure: the deployment does not start, and the reason is a JSON
        decode error several frames from anything they wrote.

        `NoDecode` on the field is what lets this run at all — without it the
        JSON parse happens in the settings source, before any validator.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return stripped  # a JSON array; let the normal parser have it
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

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
    # The fourth mechanism, built because the ablation showed the first three
    # were blind to unwarranted inference — and switched OFF by the ablation
    # that measured it (docs/adr/014).
    #
    # On the demo corpus it changed no decisions, added 24% to the cost of every
    # question, and made a third serial provider call that showed up as errors
    # the other arms did not have. It did catch a numeric contradiction on the
    # adversarial set that the shipped configuration answered confidently and
    # wrongly, which is why the code stays.
    #
    # Turning it on is one environment variable. Doing so by default would mean
    # paying on every question for a check that earns its place on documents
    # this project cannot yet show are common.
    enable_entailment_check: bool = False
    enable_query_rewrite: bool = True
    enable_rerank: bool = False

    # Refuse a question nothing retrieved is close enough to answer, before any
    # model is called. Measured over 106 questions: it fired on 0 of 49
    # answerable ones and 18 of 18 unrelated ones. It deliberately does not fire
    # on a question the document is about but does not answer — those overlap
    # the answerable distribution completely, and the prompt handles them.
    # See `api/retrieval/floor.py` for the distribution it was derived from.
    enable_retrieval_floor: bool = True

    # --- CORS ----------------------------------------------------------------
    # The browser talks to the API same-origin through a Next.js rewrite, so this
    # is normally empty. Populated only for local split-origin development.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

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
    def _prices_carry_a_verification_date(self) -> Settings:
        if self.model_prices and not self.model_prices_verified_on:
            raise ValueError(
                "MODEL_PRICES is set but MODEL_PRICES_VERIFIED_ON is empty. A rate "
                "nobody can date is a rate nobody checked; see api/pricing.py."
            )
        return self

    @property
    def priced_models(self) -> tuple[str, ...]:
        """Model ids this deployment will actually call.

        The breaker watches a sum. Any model in this list without a rate spends
        money that never reaches that sum, so this is the set health checks and
        the deployed-boot check ask about.
        """
        return tuple(
            model
            for model in (
                self.anthropic_model,
                self.gemini_embedding_model,
                self.gemini_fallback_model,
                self.gemini_ocr_model,
            )
            if model
        )

    @model_validator(mode="after")
    def _database_url_is_parseable(self) -> Settings:
        """Catch an unencoded password before asyncpg does.

        A Postgres password containing `@` or `:` must be percent-encoded in a
        connection URI. Unencoded, the `@` is read as the userinfo/host
        separator and everything shifts: the host becomes a fragment of the
        password and the port becomes garbage. asyncpg then fails deep in its
        own parser with `invalid literal for int() with base 10: 'uF'` — a
        message that says nothing about passwords and sends you looking at the
        wrong thing entirely.

        This turns that into a message naming the actual problem, at startup.
        """
        if not self.database_url:
            return self

        from urllib.parse import urlparse

        try:
            parsed = urlparse(self.database_url)
            port = parsed.port  # raises if the port is not an integer
        except ValueError as exc:
            raise ValueError(
                "DATABASE_URL could not be parsed. The usual cause is a password "
                "containing a character that must be percent-encoded in a URI "
                "(@ : / ? # [ ] %). Encode just the password:\n"
                '  python -c "import urllib.parse,getpass; '
                "print(urllib.parse.quote(getpass.getpass(), safe=''))\"\n"
                f"Underlying error: {exc}"
            ) from exc

        if not parsed.hostname or port is None:
            raise ValueError(
                "DATABASE_URL is missing a host or port. Expected the form "
                "postgresql://user:password@host:port/database"
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
