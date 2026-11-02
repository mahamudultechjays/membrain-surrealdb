"""MemoryGraph adapters for SurrealDB Agent Memory."""

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from surrealdb_memory import AsyncMemory, MemoryNotFoundError

from app.domain.errors import (
    EntityNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
)
from app.domain.ports.memory_graph import EntityFact, EntityGraph, GraphEdge, GraphNode

logger = logging.getLogger(__name__)


class AgentMemoryGraph:
    """Reads `GET /entities/search`, `.../neighbourhood` and the entity itself.

    The SDK has no wrapper for search or neighbourhood, so those go through
    its transport directly. The SDK's typed entity model also drops each
    record's `source`, which says whether Agent Memory derived a relation on
    its own, so the entity is read raw as well.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def search(self, query: str, limit: int) -> list[GraphNode]:
        body = await self._get("/entities/search", {"q": query, "limit": limit})
        return [_node(m.get("entity", {}), m.get("factCount")) for m in body.get("matches", [])]

    async def neighbourhood(self, entity_type: str, name: str, limit: int) -> EntityGraph:
        path = f"/entities/{quote(entity_type, safe='')}/{quote(name, safe='')}"
        entity, around = await asyncio.gather(
            self._get(path, {}), self._get(f"{path}/neighbourhood", {"limit": limit})
        )
        center = _node(entity.get("entity", {}), None)
        provenance = {r.get("id"): r.get("source") or {} for r in entity.get("relations", [])}

        nodes = [center]
        edges = []
        for hop in around.get("neighbours", []):
            far = hop.get("far", {})
            node = _node(far.get("entity", {}), far.get("factCount"))
            nodes.append(node)
            source = provenance.get(hop.get("relationId"), {})
            outbound = bool(hop.get("outbound"))
            edges.append(
                GraphEdge(
                    id=str(hop.get("relationId") or f"{center.id}-{node.id}"),
                    source=center.id if outbound else node.id,
                    target=node.id if outbound else center.id,
                    label=str(hop.get("label", "")),
                    source_kind=source.get("kind"),
                    trust=source.get("trust"),
                )
            )
        facts = [
            EntityFact(
                key=str(a.get("key", "")),
                value=str(a.get("value", "")),
                memory_category=str(a.get("memoryCategory", "")),
                source_kind=(a.get("source") or {}).get("kind"),
            )
            for a in entity.get("attributes", [])
        ]
        return EntityGraph(center=center, nodes=_unique(nodes), edges=edges, facts=facts)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            body = await self._client._transport.request(
                "GET",
                f"{self._client._base}{path}",
                params=params or None,
            )
        except MemoryNotFoundError as exc:
            raise EntityNotFoundError(path) from exc
        except Exception as exc:
            logger.warning("Agent Memory graph read failed", exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        return body if isinstance(body, dict) else {}


class NotConfiguredGraph:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def search(self, query: str, limit: int) -> list[GraphNode]:
        raise MemoryNotConfiguredError

    async def neighbourhood(self, entity_type: str, name: str, limit: int) -> EntityGraph:
        raise MemoryNotConfiguredError


def _node(raw: dict[str, Any], fact_count: Any) -> GraphNode:
    return GraphNode(
        name=str(raw.get("name", "")),
        entity_type=str(raw.get("entityType", "")),
        memory_category=str(raw.get("memoryCategory", "")),
        fact_count=fact_count if isinstance(fact_count, int) else None,
    )


def _unique(nodes: list[GraphNode]) -> list[GraphNode]:
    seen: dict[str, GraphNode] = {}
    for node in nodes:
        seen.setdefault(node.id, node)
    return list(seen.values())
