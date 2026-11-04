"""Port for reading everything memory holds: entities, their facts and relations.

Facts and relations carry the scope they were written to; entities do not, so
an entity belongs to the scopes its facts and relations were written in.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BrainEntity:
    # "concept/tier_a_products": the type and key facts refer to it by.
    ref: str
    name: str
    entity_type: str
    category: str


@dataclass(frozen=True, slots=True)
class BrainSource:
    """Where a fact came from: e.g. kind "turn" (a captured input) or
    "elaboration" (inferred while processing one)."""

    kind: str | None = None
    ref: str | None = None
    session_id: str | None = None
    trust: float | None = None


@dataclass(frozen=True, slots=True)
class BrainFact:
    id: str
    entity_ref: str
    key: str
    value: str
    category: str
    scopes: tuple[str, ...]
    created_at: str
    # Set when a newer value replaced this one.
    superseded_by: str | None = None
    # Agent Memory's one-sentence version of the fact; None when it has none.
    summary: str | None = None
    # Descriptive tags, e.g. "source=email"; empty when it has none.
    labels: tuple[str, ...] = ()
    confidence: float | None = None
    importance: float | None = None
    # The older fact this one replaced.
    supersedes: str | None = None
    # When the fact holds true, if Agent Memory knows.
    valid_from: str | None = None
    valid_until: str | None = None
    source: BrainSource = BrainSource()


@dataclass(frozen=True, slots=True)
class BrainRelation:
    id: str
    subject_ref: str
    label: str
    object_ref: str
    category: str
    scopes: tuple[str, ...]
    created_at: str
    summary: str | None = None
    labels: tuple[str, ...] = ()
    confidence: float | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    source: BrainSource = BrainSource()


@dataclass(frozen=True, slots=True)
class BrainSnapshot:
    entities: list[BrainEntity] = field(default_factory=list)
    facts: list[BrainFact] = field(default_factory=list)
    relations: list[BrainRelation] = field(default_factory=list)


class MemoryBrain(Protocol):
    async def snapshot(self) -> BrainSnapshot:
        """Every entity, fact and relation in the context.

        Raises MemoryNotConfiguredError or MemoryUnavailableError.
        """
        ...
