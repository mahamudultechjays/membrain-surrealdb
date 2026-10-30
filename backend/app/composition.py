"""Composition root: the only module that binds concrete adapters to ports."""

from functools import lru_cache

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory import AgentMemoryProbe, NotConfiguredProbe
from app.core.config import settings
from app.domain.ports.memory_probe import MemoryProbe


@lru_cache
def get_agent_memory_client() -> AsyncMemory | None:
    """One client per process, or None until all AGENT_MEMORY_* settings are set.

    The client opens its HTTP session lazily on first use; the app lifespan
    closes it on shutdown.
    """
    endpoint = settings.AGENT_MEMORY_ENDPOINT
    context = settings.AGENT_MEMORY_CONTEXT
    api_key = settings.AGENT_MEMORY_API_KEY
    if not (endpoint and context and api_key and api_key.get_secret_value()):
        return None
    return AsyncMemory(
        context,
        endpoint=endpoint.rstrip("/"),
        api_key=api_key.get_secret_value(),
        timeout=settings.AGENT_MEMORY_TIMEOUT_SECONDS,
    )


def get_memory_probe() -> MemoryProbe:
    client = get_agent_memory_client()
    return AgentMemoryProbe(client) if client else NotConfiguredProbe()
