"""Ask schemas: facts grouped by the memory layer they were read from."""

from typing import Literal

from pydantic import BaseModel

AskModeName = Literal["default", "best_match", "by_layer"]


class FactProvenanceOut(BaseModel):
    """Where an attribute came from and how far Agent Memory trusts it."""

    # By how it was written: 0.95 upsert, 0.5 extracted from a chat turn, 0.35 consolidated.
    trust: float | None = None
    # How sure the writer was of this value.
    confidence: float | None = None
    # upsert, turn or consolidation.
    source_kind: str | None = None
    created_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    # Set when a newer value replaced this one.
    superseded_by: str | None = None


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
    # Recall rank score for this query. It is not trust: see `provenance`.
    score: float
    # When the remembered event happened (memory chunks only).
    occurred_at: str | None = None
    # Attribute hits that match the question: trust, confidence and history,
    # read from the entity record. Null for other hits or when the lookup failed.
    provenance: FactProvenanceOut | None = None


class AskFact(BaseModel):
    fact: str
    source: FactSource
    # best_match only: whether this fact's value was used or set aside, and why.
    status: Literal["used", "set_aside"] | None = None
    reason: str | None = None
    # by_layer and best_match: the conflict this fact takes part in, if any.
    conflict_id: str | None = None


class AskLayer(BaseModel):
    layer: str
    area: str
    # Demo user name for a personal layer, else null.
    owner: str | None
    facts: list[AskFact]
    # Set when this layer's recall failed; other layers are still returned.
    error: str | None


class ConflictValueOut(BaseModel):
    value: str
    layers: list[str]
    areas: list[str]
    hit_ids: list[str]
    best_score: float


class AskConflict(BaseModel):
    """One point on which scopes hold different values."""

    id: str
    entity: str
    key: str
    # Highest-scoring value first.
    values: list[ConflictValueOut]
    # best_match only: the hit whose value was chosen, and why.
    winner_hit_id: str | None = None
    reason: str | None = None


class AskMetadata(BaseModel):
    total_facts: int
    resolution_tier: str | None
    latency_ms: int
    include_inferred: bool
    trace_ids: list[str]
    # best_match only: the tie margin applied.
    tie_margin: float | None = None


class AskResponse(BaseModel):
    q: str
    scopes: list[str]
    answered_at: str
    layers: list[AskLayer]
    metadata: AskMetadata
    trace_id: str | None
    mode: AskModeName
    # "request" when the caller named the mode, "config" when ASK_MODE_DEFAULT chose it,
    # "compare" when /ask/compare asked for it alongside the other mode.
    mode_source: Literal["request", "config", "compare"]
    # Empty for default.
    conflicts: list[AskConflict] = []


class AskCompareResponse(BaseModel):
    """Best match and By layer for one question, both from the same recall."""

    q: str
    best_match: AskResponse
    by_layer: AskResponse
