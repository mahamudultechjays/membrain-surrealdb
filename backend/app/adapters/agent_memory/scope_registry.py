"""ScopeRegistry adapters for SurrealDB Agent Memory."""

import logging
from typing import Any

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError

logger = logging.getLogger(__name__)


class AgentMemoryScopeRegistry:
    """`GET /scopes` (paged) and `POST /scopes` with the admin key.

    The listing is read raw: the pinned SDK's `scopes.list()` cannot decode the
    `{scopes, page}` envelope the server returns. Deleted (tombstoned) paths are
    left out, since a write to one fails like a write to an unknown path.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def list(self, prefix: str = "") -> list[str]:
        paths: list[str] = []
        cursor: str | None = None
        try:
            while True:
                page: dict[str, Any] = await self._client.scopes._transport.request(
                    "GET", self._client.scopes._base, params={"cursor": cursor} if cursor else None
                )
                for node in page.get("scopes", []):
                    path = str(node.get("path", "")).rstrip("/")
                    if path and node.get("tombstonedAt") is None and path.startswith(prefix):
                        paths.append(path)
                more = page.get("page") or {}
                cursor = more.get("nextCursor")
                if not (more.get("hasMore") and cursor):
                    return paths
        except Exception as exc:
            logger.warning("Agent Memory scope listing failed", exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc

    async def ensure(self, path: str) -> None:
        path = path.strip("/")
        parts = path.split("/")
        wanted = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        existing = set(await self.list(parts[0]))
        for step in wanted:
            if step in existing:
                continue
            try:
                await self._client.scopes.register(step, description="Registered by membrain POC")
            except Exception as exc:
                logger.warning("Agent Memory scope register %s failed", step, exc_info=True)
                raise MemoryUnavailableError(str(exc)) from exc


class NotConfiguredScopeRegistry:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def list(self, prefix: str = "") -> list[str]:
        raise MemoryNotConfiguredError

    async def ensure(self, path: str) -> None:
        raise MemoryNotConfiguredError
