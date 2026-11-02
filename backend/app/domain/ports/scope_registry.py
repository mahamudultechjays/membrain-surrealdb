"""Port for the scope paths registered in memory. A path must exist before a write."""

from typing import Protocol


class ScopeRegistry(Protocol):
    async def list(self, prefix: str = "") -> list[str]:
        """Live (not deleted) registered paths that start with `prefix`, without
        the trailing slash memory adds."""
        ...

    async def ensure(self, path: str) -> None:
        """Register `path` (and any missing parent) unless it already exists."""
        ...
