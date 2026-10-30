"""Port for checking that the backing database is reachable."""

from typing import Protocol


class DatabaseProbe(Protocol):
    """Answers whether the database can serve requests right now."""

    async def ping(self) -> bool:
        """Return True when the database responds, False otherwise. Never raises."""
        ...
