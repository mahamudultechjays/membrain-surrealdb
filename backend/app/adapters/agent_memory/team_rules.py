"""TeamRuleWriter: the only path that writes to the promotion team scope.

Uses a key minted for that one scope (read and write, never forget). Labels go
on every write, since a new value does not inherit them (check S3).
"""

from collections.abc import Callable
from typing import Any

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory.scoped_keys import ScopedKeys
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError

_HOLDER = "promotion-approval"
_MAX_PAGES = 20


def _id(attribute: Any) -> str:
    """The attribute id, from the SDK's dict or object form."""
    raw = attribute.get("id") if isinstance(attribute, dict) else getattr(attribute, "id", "")
    return str(raw or "").removeprefix("attribute:")


def _name(entity: str) -> str:
    """'entity:organisation/fernway_ceramics' or 'Fernway Ceramics' -> 'fernway_ceramics'."""
    last = entity.removeprefix("entity:").strip("[]' ").replace("'", "").split("/")[-1]
    last = last.split(",")[-1].strip()
    return "_".join(last.lower().split())


def _scopes(raw: Any) -> set[str]:
    return {
        str(p).strip("/")
        for clause in raw or []
        for p in (clause if isinstance(clause, list) else [clause])
    }


class AgentMemoryTeamRules:
    def __init__(
        self, admin: AsyncMemory, connect: Callable[[str], AsyncMemory], *, scope: str
    ) -> None:
        self._keys = ScopedKeys(admin, connect, prefix="membrain-promotion")
        self._scope = scope.strip("/")

    async def write(
        self, *, entity_type: str, entity: str, key: str, value: str, labels: list[str]
    ) -> str:
        grants = {"memory:read": [self._scope], "memory:write": [self._scope]}
        client = await self._keys.client_for(_HOLDER, grants)
        triple = {"entity": {"name": entity, "type": entity_type}, "key": key, "value": value}
        try:
            response: Any = await client.remember(
                infer="triples",
                triples=[triple],
                scopes=[self._scope],
                memory_category="knowledge",
                labels=labels,
            )
        except Exception as exc:
            raise MemoryUnavailableError(str(exc)) from exc
        attributes = getattr(getattr(response, "extraction", None), "attributes", None) or []
        if attributes:
            return _id(attributes[0])
        # Nothing new: the same fact is already in the scope (Agent Memory skips an
        # identical triple, seen 10 Nov after a retried approve). Use that one.
        existing = await self._find(client, entity=entity, key=key, value=value)
        if existing is None:
            raise MemoryUnavailableError("Agent Memory stored no attribute for the rule")
        return existing

    async def _find(self, client: Any, *, entity: str, key: str, value: str) -> str | None:
        """The current team-scope attribute with this entity, key and value."""
        wanted = _name(entity)
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            try:
                body: Any = await client._transport.request(
                    "GET", f"{client._base}/attributes", params=params
                )
            except Exception as exc:
                raise MemoryUnavailableError(str(exc)) from exc
            for raw in body.get("attributes") or []:
                if (
                    raw.get("key") == key
                    and str(raw.get("value")) == value
                    and _name(str(raw.get("entity") or "")) == wanted
                    and not raw.get("supersededBy")
                    and self._scope in _scopes(raw.get("scope"))
                ):
                    return _id(raw)
            page = body.get("page") or {}
            cursor = page.get("nextCursor") if page.get("hasMore") else None
            if cursor is None:
                return None
        return None

    async def close(self) -> None:
        await self._keys.close()


class NotConfiguredTeamRules:
    async def write(
        self, *, entity_type: str, entity: str, key: str, value: str, labels: list[str]
    ) -> str:
        raise MemoryNotConfiguredError("AGENT_MEMORY_* settings are missing")

    async def close(self) -> None:
        return None
