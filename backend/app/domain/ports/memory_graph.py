"""Port for reading memory as a graph: entities as nodes, relations as edges."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GraphNode:
    name: str
    entity_type: str
    memory_category: str = ""
    fact_count: int | None = None

    @property
    def id(self) -> str:
        return f"{self.entity_type}/{self.name}"


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str  # GraphNode.id
    target: str  # GraphNode.id
    label: str
    # Where the relation came from (turn, document, upsert, elaboration, ...).
    source_kind: str | None = None
    trust: float | None = None

    @property
    def derived(self) -> bool:
        """Added by Agent Memory on its own rather than said by someone."""
        return self.source_kind in {"elaboration", "consolidation", "reflect"}


@dataclass(frozen=True, slots=True)
class EntityFact:
    key: str
    value: str
    memory_category: str = ""
    source_kind: str | None = None


@dataclass(frozen=True, slots=True)
class EntityGraph:
    center: GraphNode
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    facts: list[EntityFact] = field(default_factory=list)


class MemoryGraph(Protocol):
    async def search(self, query: str, limit: int) -> list[GraphNode]:
        """Entities whose names match the query."""
        ...

    async def neighbourhood(self, entity_type: str, name: str, limit: int) -> EntityGraph:
        """One entity, its facts, and everything one relation away."""
        ...
