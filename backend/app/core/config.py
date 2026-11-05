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
    # VCT onboarding: the metro-map nodes live here as passages for matching.
    # No user is granted this scope.
    VCT_SCOPE: str = "org/spreetail/vct"

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


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, so the environment is read once."""
    return Settings()


settings = get_settings()
