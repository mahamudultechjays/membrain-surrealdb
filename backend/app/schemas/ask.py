"""Ask schemas: facts grouped by the memory layer they were read from."""

from pydantic import BaseModel


class FactSource(BaseModel):
    # "document" for document passages, "memory" for extracted facts.
    kind: str
    # Agent Memory's own hit kind: entity, attribute, memory_chunk, chunk or section.
    hit_kind: str
    hit_id: str
    # Recall hits carry no title, location or date; null until looked up.
    title: str | None = None
    location: str | None = None
    date: str | None = None
    quote: str
    # Recall score, used as a stand-in for trust.
    trust: float


class AskFact(BaseModel):
    fact: str
    source: FactSource


class AskLayer(BaseModel):
    layer: str
    area: str
    # Demo user name for a personal layer, else null.
    owner: str | None
    facts: list[AskFact]
    # Set when this layer's recall failed; other layers are still returned.
    error: str | None


class AskMetadata(BaseModel):
    total_facts: int
    resolution_tier: str | None
    latency_ms: int
    # Agent Memory does not report token cost; null until it does.
    query_cost_tokens: int | None = None
    include_inferred: bool
    trace_ids: list[str]


class AskResponse(BaseModel):
    q: str
    scopes: list[str]
    answered_at: str
    layers: list[AskLayer]
    metadata: AskMetadata
    trace_id: str | None
