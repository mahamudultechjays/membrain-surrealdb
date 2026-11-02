"""MemoryRecall adapters for SurrealDB Agent Memory."""

import logging

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import RecallHit, RecallResult

logger = logging.getLogger(__name__)


class AgentMemoryRecall:
    """`POST /query` with a lens on one scope path.

    Agent Memory clamps the lens to the key's grant, so with a user's own key
    a layer outside that user's grant comes back empty rather than leaking.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        try:
            response = await self._client.recall(
                query, k=k, lens=[lens], include=["facts", "passages"]
            )
        except Exception as exc:
            logger.warning("Agent Memory recall (lens=%s) failed", lens, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        trace_id = response.trace.get("traceId") or response.trace.get("trace_id")
        return RecallResult(
            hits=[RecallHit(h.id, h.text, h.source, h.score) for h in response.hits],
            tier=response.tier,
            query_ms=response.query_ms,
            trace_id=str(trace_id) if trace_id else None,
        )


class NotConfiguredRecall:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        raise MemoryNotConfiguredError
