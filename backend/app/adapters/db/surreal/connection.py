"""SurrealDB connection lifecycle, and the DatabaseProbe adapter built on it."""

import asyncio
import contextlib
import logging

from surrealdb import AsyncSurreal
from surrealdb.connections.async_template import AsyncTemplate

logger = logging.getLogger(__name__)


class SurrealConnection:
    """One long-lived SurrealDB client per process.

    Opened in the app lifespan and closed on shutdown, so request handlers
    share a single authenticated connection instead of reconnecting per call.

    A failed call discards the client and the next `get_client()` reconnects.
    Without that, a SurrealDB restart leaves the process holding a dead
    websocket and every request fails until the API itself is restarted.
    """

    def __init__(
        self,
        url: str,
        namespace: str,
        database: str,
        username: str,
        password: str,
    ) -> None:
        self._url = url
        self._namespace = namespace
        self._database = database
        self._username = username
        self._password = password
        self._client: AsyncTemplate | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        await self.get_client()

    async def get_client(self) -> AsyncTemplate:
        """The open client, connecting first if there is none."""
        async with self._lock:
            if self._client is None:
                client = AsyncSurreal(self._url)
                await client.connect(self._url)
                await client.signin({"username": self._username, "password": self._password})
                await client.use(self._namespace, self._database)
                self._client = client
                logger.info(
                    "Connected to SurrealDB at %s (%s/%s)",
                    self._url,
                    self._namespace,
                    self._database,
                )
            return self._client

    async def discard(self) -> None:
        """Drop the current client so the next call reconnects."""
        async with self._lock:
            client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.close()

    async def close(self) -> None:
        await self.discard()

    async def ping(self) -> bool:
        try:
            client = await self.get_client()
            await client.query("RETURN true")
        except Exception:
            logger.warning("SurrealDB ping failed; will reconnect on next call", exc_info=True)
            await self.discard()
            return False
        return True
