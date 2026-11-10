"""Port for where a remembered fact came from and how far it is trusted."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FactProvenance:
    """One attribute's provenance, as Agent Memory stores it.

    `trust` follows how the fact was written: 0.95 for a structured upsert,
    0.5 for one extracted from a chat turn, 0.35 for one consolidated from
    others (seen live, 9 Nov 2026). `confidence` is how sure the writer was.
    """

    trust: float | None = None
    confidence: float | None = None
    # How it was written: upsert, turn or consolidation.
    source_kind: str | None = None
    created_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    # The newer attribute that replaced this one, if any.
    superseded_by: str | None = None


class FactProvenanceReader(Protocol):
    async def attributes(self, entity_type: str, entity_name: str) -> dict[str, FactProvenance]:
        """Provenance of every attribute of one entity, by attribute id.

        The entity is read across all scopes, so callers must keep only the
        attributes they were already allowed to see (the recalled hits).
        """
        ...
