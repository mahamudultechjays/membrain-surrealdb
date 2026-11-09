"""Ask schemas: one recall's hits, in the order Agent Memory ranked them."""

from pydantic import BaseModel


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


class AskMetadata(BaseModel):
    total_facts: int
    resolution_tier: str | None
    latency_ms: int
    include_inferred: bool
    trace_ids: list[str]


class AskResponse(BaseModel):
    q: str
    # The scopes the recall read, org first, then team, then personal.
    scopes: list[str]
    answered_at: str
    # Agent Memory's ranking across all those scopes. Hits carry no scope.
    facts: list[AskFact]
    metadata: AskMetadata
    trace_id: str | None
