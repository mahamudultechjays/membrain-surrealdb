"""Port for storing text in memory as-is, with no fact extraction."""

from typing import Protocol


class PassageWriter(Protocol):
    async def write(self, text: str, scope: str) -> None:
        """Store `text` as one passage in `scope`, findable by recall."""
        ...
