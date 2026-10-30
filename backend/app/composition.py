"""Composition root: the only module that binds concrete adapters to ports."""

from functools import lru_cache

from app.adapters.db.surreal import SurrealConnection
from app.core.config import settings
from app.domain.ports.database_probe import DatabaseProbe


@lru_cache
def get_surreal_connection() -> SurrealConnection:
    return SurrealConnection(
        url=settings.SURREAL_URL,
        namespace=settings.SURREAL_NAMESPACE,
        database=settings.SURREAL_DATABASE,
        username=settings.SURREAL_USER,
        password=settings.SURREAL_PASSWORD.get_secret_value(),
    )


def get_database_probe() -> DatabaseProbe:
    return get_surreal_connection()
