"""Graph schemas: entities as nodes, relations as edges."""

from pydantic import BaseModel, ConfigDict


class _FromDomain(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NodeOut(_FromDomain):
    id: str
    name: str
    entity_type: str
    memory_category: str
    fact_count: int | None


class EdgeOut(_FromDomain):
    id: str
    source: str
    target: str
    label: str
    source_kind: str | None
    trust: float | None
    derived: bool


class FactOut(_FromDomain):
    key: str
    value: str
    memory_category: str
    source_kind: str | None


class SearchResponse(BaseModel):
    entities: list[NodeOut]


class NeighbourhoodResponse(_FromDomain):
    center: NodeOut
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    facts: list[FactOut]
