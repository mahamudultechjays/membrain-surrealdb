"""MemoryRecall and FactProvenanceReader adapters for SurrealDB Agent Memory."""

import logging
from typing import Any
from urllib.parse import quote

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.fact_provenance import FactProvenance
from app.domain.ports.memory_recall import RecallHit, RecallResult

logger = logging.getLogger(__name__)


class AgentMemoryRecall:
    """`POST /query` with a lens on one scope path.

    Agent Memory clamps the lens to the key's grant, so with a user's own key
    a layer outside that user's grant comes back empty rather than leaking.

    Read raw rather than through `client.recall`: the SDK's hit model keeps
    only id, score, source and text, and drops `resource` (the attribute's
    entity and key) and `occurredAt`, which provenance needs.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        payload = {"query": query, "k": k, "lens": [[lens]], "include": ["facts", "passages"]}
        try:
            raw: dict[str, Any] = await self._client._transport.request(
                "POST", f"{self._client._base}/query", json=payload
            )
        except Exception as exc:
            logger.warning("Agent Memory recall (lens=%s) failed", lens, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        trace = raw.get("trace") or {}
        trace_id = trace.get("traceId") or trace.get("trace_id")
        return RecallResult(
            hits=[_hit(h) for h in raw.get("hits") or []],
            tier=str(raw.get("tier") or ""),
            query_ms=int(raw.get("queryMs") or 0),
            trace_id=str(trace_id) if trace_id else None,
        )


def _hit(raw: dict[str, Any]) -> RecallHit:
    resource = raw.get("resource") or {}
    attribute = resource.get("kind") == "attribute"
    return RecallHit(
        id=str(raw.get("id", "")),
        text=str(raw.get("text", "")),
        kind=str(raw.get("source", "")),
        score=float(raw.get("score") or 0.0),
        entity_type=resource.get("entityType") if attribute else None,
        entity_name=resource.get("name") if attribute else None,
        key=resource.get("key") if attribute else None,
        occurred_at=raw.get("occurredAt"),
    )


class AgentMemoryFactProvenance:
    """`GET /entities/{type}/{name}`: each attribute's trust, confidence and history.

    Read raw: the SDK's AttributeDetail drops `confidence` and `source`
    (`{kind, trust}`). The response spans every scope, so the caller filters it.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def attributes(self, entity_type: str, entity_name: str) -> dict[str, FactProvenance]:
        path = (
            f"{self._client._base}/entities/"
            f"{quote(entity_type, safe='')}/{quote(entity_name, safe='')}"
        )
        try:
            raw: dict[str, Any] = await self._client._transport.request("GET", path)
        except Exception as exc:
            raise MemoryUnavailableError(str(exc)) from exc
        out: dict[str, FactProvenance] = {}
        for attr in raw.get("attributes") or []:
            source = attr.get("source") or {}
            out[str(attr.get("id", ""))] = FactProvenance(
                trust=_number(source.get("trust")),
                confidence=_number(attr.get("confidence")),
                source_kind=source.get("kind"),
                created_at=attr.get("createdAt"),
                valid_from=attr.get("validFrom"),
                valid_until=attr.get("validUntil"),
                superseded_by=attr.get("supersededBy"),
            )
        return out


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


class NotConfiguredRecall:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        raise MemoryNotConfiguredError


class NotConfiguredFactProvenance:
    """No provenance without Agent Memory; answers still work without it."""

    async def attributes(self, entity_type: str, entity_name: str) -> dict[str, FactProvenance]:
        return {}
