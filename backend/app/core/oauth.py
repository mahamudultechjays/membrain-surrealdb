"""Authlib OAuth client for Entra ID SSO, built only when AZURE_* is configured."""

from functools import lru_cache
from typing import Any

from authlib.integrations.starlette_client import OAuth

from app.core.config import settings


@lru_cache
def get_oauth_client() -> Any | None:
    """The registered Entra OIDC client, or None so login falls back to dev login."""
    if not settings.sso_configured or settings.AZURE_CLIENT_SECRET is None:
        return None
    oauth = OAuth()
    oauth.register(
        name="azure",
        server_metadata_url=settings.azure_metadata_url,
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET.get_secret_value(),
        client_kwargs={"scope": settings.AZURE_LOGIN_SCOPE},
    )
    return oauth.azure
