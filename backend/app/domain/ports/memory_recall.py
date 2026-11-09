"""Port for searching memory across scope paths in one recall."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RecallHit:
    id: str
    text: str
    # What the hit is: entity, attribute, memory_chunk, chunk or section.
    kind: str
    score: float
    # For a memory chunk: the captured turn it is part of; facts extracted
    # from that turn point to it too.
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecallResult:
    hits: list[RecallHit] = field(default_factory=list)
    # How memory resolved the query: direct, cache, hybrid or escalated.
    tier: str = ""
    query_ms: int = 0
    trace_id: str | None = None


class MemoryRecall(Protocol):
    async def recall(self, query: str, *, lenses: Sequence[str], k: int) -> RecallResult:
        """Facts and passages matching `query`, read only from `lenses`, ranked as one list."""
        ...
