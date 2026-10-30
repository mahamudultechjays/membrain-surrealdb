"""Port for checking that the memory service can serve requests."""

from typing import Literal, Protocol

MemoryStatus = Literal["ok", "unavailable", "not_configured"]


class MemoryProbe(Protocol):
    """Answers whether the memory service is usable right now."""

    async def check(self) -> MemoryStatus:
        """Never raises: every failure maps to a status."""
        ...
