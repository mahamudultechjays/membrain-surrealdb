"""Port for writing a team rule (or its closing value) to the team scope."""

from typing import Protocol


class TeamRuleWriter(Protocol):
    async def write(
        self, *, entity_type: str, entity: str, key: str, value: str, labels: list[str]
    ) -> str:
        """Stores one knowledge triple in the team scope; returns the attribute id."""
        ...
