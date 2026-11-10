"""FactLister on Agent Memory's GET /attributes listing.

The listing takes no scope filter, but a key's own grants clamp what it lists
(seen live 2026-11-04), so each call uses a key minted for read on exactly the
scopes being tagged. Callers still check each fact's scopes.
"""

import logging
import re
from collections.abc import Callable
from typing import Any

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory.scoped_keys import ScopedKeys
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.fact_lister import ListedFact, ListedPage

logger = logging.getLogger(__name__)

_HOLDER = "vct-tagger"
# "entity:person/person/kiran_rao" or "['organisation', 'gatetest_omega']" -> the name.
_ENTITY_NAME = re.compile(r"([^/'\[\],\s]+)'?\s*\]?\s*$")


class AgentMemoryFactLister:
    def __init__(
        self,
        admin: AsyncMemory,
        connect: Callable[[str], AsyncMemory],
        *,
        holder: str = _HOLDER,
        prefix: str = "membrain-tagger",
    ) -> None:
        self._keys = ScopedKeys(admin, connect, prefix=prefix)
        self._holder = holder

    async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
        if not scopes:
            return ListedPage()
        client = await self._keys.client_for(self._holder, {"memory:read": sorted(scopes)})
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        try:
            body: Any = await client._transport.request(
                "GET", f"{client._base}/attributes", params=params
            )
        except Exception as exc:
            logger.warning("Agent Memory attribute listing failed", exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        more = body.get("page") or {}
        return ListedPage(
            facts=[f for raw in body.get("attributes", []) if (f := _fact(raw))],
            cursor=more.get("nextCursor") if more.get("hasMore") else None,
        )

    async def close(self) -> None:
        await self._keys.close()


class NotConfiguredFactLister:
    async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> ListedPage:
        raise MemoryNotConfiguredError("AGENT_MEMORY_* settings are missing")

    async def close(self) -> None:
        return None


def _fact(raw: Any) -> ListedFact | None:
    fact_id = _id(raw.get("id"))
    if not fact_id:
        return None
    source = raw.get("source")
    entity_type, entity_name = _entity(raw.get("entity"))
    return ListedFact(
        id=fact_id,
        text=_text(raw),
        scopes=_scopes(raw.get("scope")),
        supersedes=_id(raw.get("supersedes")) or None,
        turn_id=_turn(raw.get("source")),
        entity_type=entity_type,
        entity=entity_name,
        key=str(raw.get("key") or "") or None,
        value=str(raw.get("value") or "") or None,
        created_at=raw.get("createdAt"),
        source_kind=source.get("kind") if isinstance(source, dict) else None,
    )


def _entity(raw: Any) -> tuple[str | None, str | None]:
    """(type, name) from "['organisation', 'cobalt_ridge']" or
    "entity:organisation/organisation/cobalt_ridge"."""
    text = str(raw or "").removeprefix("entity:").strip("[] ")
    sep = "/" if "/" in text else ","
    bits = [b.strip().strip("'\"") for b in text.split(sep)]
    bits = [b for b in bits if b]
    if not bits:
        return None, None
    return (bits[0] if len(bits) > 1 else None), bits[-1]


def _turn(source: Any) -> str | None:
    ref = str(source.get("ref") or "") if isinstance(source, dict) else ""
    return ref.removeprefix("turn:") if ref.startswith("turn:") else None


def _id(raw: Any) -> str:
    return str(raw or "").removeprefix("attribute:")


def _text(raw: Any) -> str:
    summary = str(raw.get("summary") or "").strip()
    if summary:
        return summary
    entity = str(raw.get("entity") or "")
    name = match.group(1) if (match := _ENTITY_NAME.search(entity)) else entity
    parts = (name.replace("_", " "), str(raw.get("key") or ""), str(raw.get("value") or ""))
    return " ".join(p for p in parts if p)


def _scopes(raw: Any) -> tuple[str, ...]:
    """[['org/a/'], ['org/b/']] -> ('org/a', 'org/b'): every path, once."""
    paths: list[str] = []
    for clause in raw or []:
        for path in clause if isinstance(clause, list) else [clause]:
            clean = str(path).strip("/")
            if clean and clean not in paths:
                paths.append(clean)
    return tuple(paths)
