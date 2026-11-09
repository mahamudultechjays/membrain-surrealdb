"""MemoryRecall adapters for SurrealDB Agent Memory."""

import logging
from collections.abc import Sequence
from typing import Any

from surrealdb_memory import AsyncMemory
from surrealdb_memory._models.memory import RecallResponse

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import RecallHit, RecallResult

logger = logging.getLogger(__name__)


class AgentMemoryRecall:
    """`POST /query` with a lens on each scope path, answered as one ranked list.

    Agent Memory clamps the lens to the key's grant, so with a user's own key
    a layer outside that user's grant comes back empty rather than leaking.
    The raw response is read because the SDK drops each hit's `resource`,
    which names the turn a memory chunk came from.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def recall(self, query: str, *, lenses: Sequence[str], k: int) -> RecallResult:
        body = {"query": query, "k": k, "lens": list(lenses), "include": ["facts", "passages"]}
        try:
            raw: Any = await self._client._transport.request(
                "POST", f"{self._client._base}/query", json=body
            )
            response = RecallResponse.from_dict(raw)
        except Exception as exc:
            logger.warning("Agent Memory recall (lens=%s) failed", lenses, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        turns = [_turn_of(h) for h in (raw.get("hits") or [])]
        trace_id = response.trace.get("traceId") or response.trace.get("trace_id")
        return RecallResult(
            hits=[
                RecallHit(h.id, h.text, h.source, h.score, turn)
                for h, turn in zip(response.hits, turns, strict=False)
            ],
            tier=response.tier,
            query_ms=response.query_ms,
            trace_id=str(trace_id) if trace_id else None,
        )


def _turn_of(raw: Any) -> str | None:
    resource = raw.get("resource") if isinstance(raw, dict) else None
    turn = resource.get("turnId") if isinstance(resource, dict) else None
    return str(turn) if turn else None


class NotConfiguredRecall:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def recall(self, query: str, *, lenses: Sequence[str], k: int) -> RecallResult:
        raise MemoryNotConfiguredError
