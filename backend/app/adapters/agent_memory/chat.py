"""MemoryChat adapter: `POST /chat` through a key minted for each user's grants.

`/chat` picks its own context, and `scopes` only says where the user's message
is stored, so with the admin key it can cite any scope (seen on 2026-11-04: a
chat scoped to one user's scope cited another user's personal facts). A key's
grants do clamp what it reads, so each owner gets a key minted from the admin
key (`POST /keys`, grants can only narrow) with read on exactly their granted
scopes and write on their personal scope. The key is reused until the owner's
access changes, then replaced; `close()` deletes every key this process minted.

The SDK's `chat()` drops `citations`, so the raw response is read instead.
"""

import asyncio
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_chat import ChatAccess, ChatCitation, ChatReply

logger = logging.getLogger(__name__)

Grants = dict[str, list[str]]


@dataclass(slots=True)
class _Key:
    name: str
    grants: Grants
    client: AsyncMemory


def _grants(access: ChatAccess) -> Grants:
    return {"memory:read": list(dict.fromkeys(access.read)), "memory:write": [access.write]}


def _key_name(owner: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", owner.lower()).strip("-")[:40] or "user"
    return f"membrain-chat-{slug}-{secrets.token_hex(3)}"


def _citation(raw: dict[str, Any]) -> ChatCitation:
    return ChatCitation(
        marker=str(raw.get("marker", "")),
        id=str(raw.get("id", "")),
        kind=str(raw.get("kind", "")),
        snippet=str(raw.get("snippet", "")),
        score=float(raw.get("score") or 0.0),
        document_title=raw.get("documentTitle"),
        position_percent=raw.get("positionPercent"),
        role=raw.get("role"),
        occurred_at=raw.get("occurredAt"),
    )


def _reply(raw: dict[str, Any]) -> ChatReply:
    updates = raw.get("memoryUpdates") or {}
    saved = sum(len(updates.get(kind) or []) for kind in ("entities", "attributes", "relations"))
    return ChatReply(
        reply=str(raw.get("reply", "")),
        session_id=str(raw.get("sessionId", "")),
        trace_id=raw.get("traceId"),
        citations=[_citation(c) for c in raw.get("citations") or []],
        facts_saved=saved,
    )


class AgentMemoryChat:
    def __init__(self, admin: AsyncMemory, connect: Callable[[str], AsyncMemory]) -> None:
        self._admin = admin
        self._connect = connect
        self._keys: dict[str, _Key] = {}
        self._lock = asyncio.Lock()

    async def chat(self, message: str, *, access: ChatAccess, session_id: str | None) -> ChatReply:
        client = await self._client_for(access)
        payload: dict[str, Any] = {"message": message, "scopes": [[access.write]]}
        if session_id:
            payload["sessionId"] = session_id
        try:
            raw = await client._transport.request("POST", f"{client._base}/chat", json=payload)
        except Exception as exc:
            logger.warning("Agent Memory chat for %s failed", access.owner, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        return _reply(raw)

    async def close(self) -> None:
        async with self._lock:
            keys, self._keys = list(self._keys.values()), {}
        for key in keys:
            await self._drop(key)

    async def _client_for(self, access: ChatAccess) -> AsyncMemory:
        grants = _grants(access)
        async with self._lock:
            current = self._keys.get(access.owner)
            if current and current.grants == grants:
                return current.client
            name = _key_name(access.owner)
            try:
                minted = await self._admin._transport.request(
                    "POST", f"{self._admin._base}/keys", json={"name": name, "grants": grants}
                )
            except Exception as exc:
                logger.warning("Minting a chat key for %s failed", access.owner, exc_info=True)
                raise MemoryUnavailableError(str(exc)) from exc
            key = _Key(name, grants, self._connect(str(minted["key"])))
            self._keys[access.owner] = key
        if current:
            await self._drop(current)
        return key.client

    async def _drop(self, key: _Key) -> None:
        """Best effort: a key left behind is narrower than the admin key anyway."""
        await key.client.close()
        try:
            await self._admin._transport.request("DELETE", f"{self._admin._base}/keys/{key.name}")
        except Exception:
            logger.warning("Deleting chat key %s failed", key.name, exc_info=True)


class NotConfiguredChat:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def chat(self, message: str, *, access: ChatAccess, session_id: str | None) -> ChatReply:
        raise MemoryNotConfiguredError

    async def close(self) -> None:
        return None
