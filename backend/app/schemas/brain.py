"""Brain schemas: entities with their facts and relations, filtered by scope."""

from pydantic import BaseModel


class BrainSourceOut(BaseModel):
    # e.g. "turn" (a captured input) or "elaboration" (inferred from one).
    kind: str | None
    ref: str | None
    session_id: str | None
    trust: float | None


class BrainFactOut(BaseModel):
    id: str
    # The entity's type and key, e.g. "concept/tier_a_products".
    entity_ref: str
    key: str
    value: str
    category: str
    scopes: list[str]
    created_at: str
    # True when a newer value replaced this one.
    replaced: bool
    # Agent Memory's one-sentence version of the fact; null when it has none.
    summary: str | None
    # Descriptive tags such as "source=email"; empty when it has none.
    labels: list[str]
    confidence: float | None
    importance: float | None
    # The fact this one replaced, and the fact that replaced this one.
    supersedes: str | None
    superseded_by: str | None
    valid_from: str | None
    valid_until: str | None
    source: BrainSourceOut


class BrainRelationOut(BaseModel):
    id: str
    subject_ref: str
    label: str
    # The related entity's ref and display name.
    object_ref: str
    object_name: str
    category: str
    scopes: list[str]
    created_at: str
    summary: str | None
    labels: list[str]
    confidence: float | None
    valid_from: str | None
    valid_until: str | None
    source: BrainSourceOut


class BrainEntityOut(BaseModel):
    ref: str
    name: str
    entity_type: str
    category: str
    # The scopes this entity's shown facts and relations were written to.
    scopes: list[str]
    updated_at: str
    facts: list[BrainFactOut]
    relations: list[BrainRelationOut]


class BrainResponse(BaseModel):
    entities: list[BrainEntityOut]
    # Every scope the caller may filter by that holds something.
    scopes: list[str]
    total_facts: int
    total_relations: int
