"""MemoryProbe adapters for SurrealDB Agent Memory."""

import logging

from surrealdb_memory import AsyncMemory

from app.domain.ports.memory_probe import MemoryStatus

logger = logging.getLogger(__name__)


class AgentMemoryProbe:
    """Checks the configured Context with an authenticated `GET /me`.

    `whoami()` rather than the unauthenticated `health()`, because only an
    authenticated call proves the endpoint, Context id and API key all work.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def check(self) -> MemoryStatus:
        try:
            await self._client.whoami()
        except Exception:
            logger.warning("Agent Memory check failed", exc_info=True)
            return "unavailable"
        return "ok"


class NotConfiguredProbe:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def check(self) -> MemoryStatus:
        return "not_configured"
