"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration in one place."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # App
    PROJECT_NAME: str = "Membrain SurrealDB POC"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # API
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5174"]

    # SurrealDB Agent Memory (hosted on SurrealDB Cloud, reached over HTTPS).
    # All three come from the Context's page in SurrealDB Cloud. Optional so the
    # app still starts on a fresh clone; readiness reports "not_configured".
    AGENT_MEMORY_ENDPOINT: str | None = None
    AGENT_MEMORY_CONTEXT: str | None = None
    AGENT_MEMORY_API_KEY: SecretStr | None = None
    AGENT_MEMORY_TIMEOUT_SECONDS: float = 30.0

    # Governance: who may read or write which Agent Memory scope. Grants live in
    # a local SQLite file; the org scope and the root for personal scopes
    # (<root>/<firstname>_<lastname>) already exist in the Context.
    USER_SCOPES_DB_PATH: str = "data/user_scopes.db"
    ORG_SCOPE: str = "org/spreetail"
    USER_SCOPE_ROOT: str = "org/spreetail/user"
    # VCT matching: the 41 metro-map nodes and 42 goals live here as passages
    # (onboarding and fact tagging recall against them). No user is granted them.
    VCT_SCOPE: str = "org/spreetail/vct/nodes"
    VCT_GOALS_SCOPE: str = "org/spreetail/vct/goals"
    # VCT tagger: tags facts with nodes and goals every TAGGER_INTERVAL_HOURS.
    # TAGGER_SCOPES is a comma-separated allowlist (exact scopes, no sub-scopes);
    # the pilot tags three personal scopes (mahamudul_hasan has no facts yet, so
    # arun_das and vidyul were added for testing, 6 Nov). TAGGER_MAX_FACTS caps one run.
    TAGGER_ENABLED: bool = True
    TAGGER_INTERVAL_HOURS: float = 3.0
    TAGGER_SCOPES: str = (
        "org/spreetail/user/mahamudul_hasan,org/spreetail/user/arun_das,org/spreetail/user/vidyul"
    )
    TAGGER_MAX_FACTS: int = 500

    # Promotion (drafts/promotion/promotion-build-spec.html, section 3). Test
    # profile for .env: PERSONAL_RULE_AT=1.5, CANDIDATE_AT=2, FLAG_AT=1,
    # BATCH_SIZE=5, JOB_EVERY_MINUTES=5.
    PROMOTION_ENABLED: bool = False
    PROMOTION_TEAM_SCOPE: str = "org/spreetail/team/common"
    PROMOTION_PERSONAL_RULE_AT: float = 1.75
    PROMOTION_CANDIDATE_AT: float = 3.0
    PROMOTION_FLAG_AT: float = 2.0
    PROMOTION_FIRST_WEIGHT: float = 1.0
    PROMOTION_REPEAT_FACTOR: float = 0.5
    PROMOTION_BATCH_SIZE: int = 20
    PROMOTION_GENERIC_SUBJECTS: str = "spreetail,our team,we,the company"
    PROMOTION_MODEL: str = "claude-haiku-5-5"
    PROMOTION_JOB_EVERY_MINUTES: float = 240
    # The small Claude model that groups statements. Unset: grouping is skipped.
    ANTHROPIC_API_KEY: SecretStr | None = None

    # Login: Entra ID SSO, as in membrain (Authlib + a signed session cookie).
    # The app registration must allow <FRONTEND_URL>/api/v1/auth/callback.
    AZURE_CLIENT_ID: str | None = None
    AZURE_CLIENT_SECRET: SecretStr | None = None
    AZURE_TENANT_ID: str | None = None
    AZURE_LOGIN_SCOPE: str = "openid profile email"
    SESSION_SECRET_KEY: SecretStr = SecretStr("dev-insecure-change-me")
    FRONTEND_URL: str = "http://localhost:5174"
    # Comma-separated emails that may use the admin endpoints.
    ADMIN_EMAILS: str = ""
    # Email-only login for local demos. Unset: on in development when SSO is not
    # configured, off otherwise.
    DEV_LOGIN_ENABLED: bool | None = None

    @property
    def sso_configured(self) -> bool:
        secret = self.AZURE_CLIENT_SECRET
        return bool(
            self.AZURE_CLIENT_ID and self.AZURE_TENANT_ID and secret and secret.get_secret_value()
        )

    @property
    def dev_login_enabled(self) -> bool:
        if self.DEV_LOGIN_ENABLED is not None:
            return self.DEV_LOGIN_ENABLED
        return self.ENVIRONMENT == "development" and not self.sso_configured

    @property
    def azure_metadata_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.AZURE_TENANT_ID}"
            "/v2.0/.well-known/openid-configuration"
        )

    @property
    def azure_redirect_uri(self) -> str:
        return f"{self.FRONTEND_URL.rstrip('/')}{self.API_V1_PREFIX}/auth/callback"

    def admin_emails(self) -> set[str]:
        """ADMIN_EMAILS, lowercased. Accepts "a@x.com,b@x.com" or '["a@x.com"]'."""
        raw = self.ADMIN_EMAILS.strip().strip("[]")
        return {e.strip().strip("'\"").lower() for e in raw.split(",") if e.strip().strip("'\"")}

    def promotion_generic_subjects(self) -> frozenset[str]:
        return frozenset(
            s.strip().lower() for s in self.PROMOTION_GENERIC_SUBJECTS.split(",") if s.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, so the environment is read once."""
    return Settings()


settings = get_settings()
