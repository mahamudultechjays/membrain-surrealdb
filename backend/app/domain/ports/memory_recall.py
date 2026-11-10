"""Port for searching memory within one scope path."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RecallHit:
    id: str
    text: str
    # What the hit is: entity, attribute, memory_chunk, chunk or section.
    kind: str
    score: float
    # For attribute hits, the record it points at, from /query's `resource`:
    # enough to look up the attribute's trust (see ports.fact_provenance).
    entity_type: str | None = None
    entity_name: str | None = None
    key: str | None = None
    # When the remembered event happened, for memory chunks; None otherwise.
    occurred_at: str | None = None


@dataclass(frozen=True, slots=True)
class RecallResult:
    hits: list[RecallHit] = field(default_factory=list)
    # How memory resolved the query: direct, cache, hybrid or escalated.
    tier: str = ""
    query_ms: int = 0
    trace_id: str | None = None


class MemoryRecall(Protocol):
    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        """Facts and passages matching `query`, read only from `lens`."""
        ...
