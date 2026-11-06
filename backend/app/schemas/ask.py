"""Ask schemas: facts grouped by the memory layer they were read from."""

from pydantic import BaseModel, Field

from app.schemas.vct_tags import FactTagsOut


class FactSource(BaseModel):
    # "document" for document passages, "memory" for extracted facts.
    kind: str
    # Agent Memory's own hit kind: entity, attribute, memory_chunk, chunk or section.
    hit_kind: str
    hit_id: str
    # Recall hits carry no title or date; null until looked up.
    title: str | None = None
    date: str | None = None
    # The hit's own text, not a verified quote from the source document.
    text: str
    # Recall rank score for this query. It is not trust: /query exposes no per-hit trust.
    score: float


class AskFact(BaseModel):
    fact: str
    source: FactSource
    # The fact's active VCT node and goal; null for untagged facts and non-facts.
    tags: FactTagsOut | None = None


class AskLayer(BaseModel):
    layer: str
    area: str
    # Demo user name for a personal layer, else null.
    owner: str | None
    facts: list[AskFact]
    # Set when this layer's recall failed; other layers are still returned.
    error: str | None
    # Facts the VCT filter dropped from this layer, for comparing with no filter.
    removed: list[AskFact] = Field(default_factory=list)


class AskFilter(BaseModel):
    goals: list[str]
    nodes: list[str]
    domains: list[str]
    removed: int = Field(description="Hits the filter dropped across all layers.")


class AskMetadata(BaseModel):
    total_facts: int
    resolution_tier: str | None
    latency_ms: int
    include_inferred: bool
    trace_ids: list[str]
    # Set when a VCT goal, node or domain filter was applied.
    filter: AskFilter | None = None


class AskResponse(BaseModel):
    q: str
    scopes: list[str]
    answered_at: str
    layers: list[AskLayer]
    metadata: AskMetadata
    trace_id: str | None
