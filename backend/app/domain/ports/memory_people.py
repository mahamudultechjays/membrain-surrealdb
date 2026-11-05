"""Port for the people Agent Memory knows: its human principals."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class MemoryPerson:
    email: str
    name: str
    # Their grants in Agent Memory: permission (e.g. "memory:read") → scope
    # patterns (e.g. ["/*"]). Read only here.
    grants: dict[str, list[str]] = field(default_factory=dict)


class MemoryPeople(Protocol):
    async def list(self) -> list[MemoryPerson]:
        """Every human principal named by an email, whether or not they use this app."""
        ...
