"""Keys minted from the admin key, each narrowed to the grants one caller needs.

A key's own grants clamp what Agent Memory reads and writes for it, while the
admin key reads everything (seen live on 2026-11-04). `POST /keys` mints a key
for the caller's principal whose grants can only narrow. One key is kept per
holder (a user, a lab scope) and reused while its grants are unchanged; when
they change it is replaced and the old one deleted. `close()` deletes them all.
"""

import asyncio
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryUnavailableError

logger = logging.getLogger(__name__)

Grants = dict[str, list[str]]


@dataclass(slots=True)
class _Key:
    name: str
    grants: Grants
    client: AsyncMemory


class ScopedKeys:
    def __init__(
        self, admin: AsyncMemory, connect: Callable[[str], AsyncMemory], *, prefix: str
    ) -> None:
        self._admin = admin
        self._connect = connect
        self._prefix = prefix
        self._keys: dict[str, _Key] = {}
        self._lock = asyncio.Lock()

    async def client_for(self, holder: str, grants: Grants) -> AsyncMemory:
        """A client whose key has exactly `grants`, minted on first use."""
        async with self._lock:
            current = self._keys.get(holder)
            if current and current.grants == grants:
                return current.client
            name = self._name(holder)
            try:
                minted = await self._admin._transport.request(
                    "POST", f"{self._admin._base}/keys", json={"name": name, "grants": grants}
                )
            except Exception as exc:
                logger.warning("Minting a key for %s failed", holder, exc_info=True)
                raise MemoryUnavailableError(str(exc)) from exc
            key = _Key(name, grants, self._connect(str(minted["key"])))
            self._keys[holder] = key
        if current:
            await self._drop(current)
        return key.client

    async def close(self) -> None:
        async with self._lock:
            keys, self._keys = list(self._keys.values()), {}
        for key in keys:
            await self._drop(key)

    def _name(self, holder: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", holder.lower()).strip("-")[:40] or "holder"
        return f"{self._prefix}-{slug}-{secrets.token_hex(3)}"

    async def _drop(self, key: _Key) -> None:
        """Best effort: a key left behind is narrower than the admin key anyway."""
        await key.client.close()
        try:
            await self._admin._transport.request("DELETE", f"{self._admin._base}/keys/{key.name}")
        except Exception:
            logger.warning("Deleting key %s failed", key.name, exc_info=True)
