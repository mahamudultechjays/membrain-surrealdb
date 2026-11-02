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


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, so the environment is read once."""
    return Settings()


settings = get_settings()
