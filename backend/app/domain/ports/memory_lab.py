"""Port for triggering memory jobs by hand: consolidate, elaborate, reflect on one scope.

Each job runs with a credential that can read and write only that scope, so a
run never pools or changes facts anywhere else. `scope=None` means the whole
Context, which only counts and consolidation (as a preview) accept.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LabCounts:
    entities: int = 0
    attributes: int = 0
    relations: int = 0
    # Attributes and relations by where they came from: turn, document,
    # elaboration, consolidation, reflect, ...
    by_source: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LabOutcome:
    """What one operation reported, ready to show."""

    # Headline numbers, e.g. {"created": 2, "updated": 0}.
    summary: dict[str, int] = field(default_factory=dict)
    # One line per record the operation created, proposed or used as evidence.
    items: list[str] = field(default_factory=list)
    # Free text, e.g. a reflection.
    text: str | None = None
    trace_ids: list[str] = field(default_factory=list)


class MemoryLab(Protocol):
    async def counts(self, scope: str | None) -> LabCounts:
        """Live entities, attributes and relations in `scope` (None: the whole Context)."""
        ...

    async def consolidate(self, scope: str | None, *, dry_run: bool) -> LabOutcome: ...

    async def elaborate(self, scope: str, *, dry_run: bool) -> LabOutcome:
        """Elaborate each entity in `scope` in turn (a full sweep does not finish)."""
        ...

    async def reflect(self, scope: str, query: str, *, persist: bool) -> LabOutcome: ...
