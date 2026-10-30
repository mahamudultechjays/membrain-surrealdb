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

    # SurrealDB. Defaults reach the compose service from the host; compose
    # overrides SURREAL_URL to use the service name inside the network.
    SURREAL_URL: str = "ws://localhost:8001/rpc"
    SURREAL_NAMESPACE: str = "membrain"
    SURREAL_DATABASE: str = "poc"
    SURREAL_USER: str = "root"
    SURREAL_PASSWORD: SecretStr = SecretStr("root")


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, so the environment is read once."""
    return Settings()


settings = get_settings()
