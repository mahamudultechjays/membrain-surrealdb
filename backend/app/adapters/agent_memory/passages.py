"""PassageWriter adapters for SurrealDB Agent Memory."""

import logging

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError

logger = logging.getLogger(__name__)


class AgentMemoryPassages:
    """`remember(infer="none")`: the text is kept verbatim and no facts are extracted."""

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def write(self, text: str, scope: str) -> None:
        try:
            await self._client.remember(text, infer="none", scopes=[scope])
        except Exception as exc:
            logger.warning("Agent Memory passage write to %s failed", scope, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc


class NotConfiguredPassages:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def write(self, text: str, scope: str) -> None:
        raise MemoryNotConfiguredError
