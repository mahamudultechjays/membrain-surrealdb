"""MemoryLab adapter: consolidate, elaborate, reflect and count on one scope.

None of these calls takes a scope. On-demand consolidation pools only the
caller's read region (REST reference), and reflection draws on "the key's
whole read region" (Reflection page), so each run uses a key minted with read
and write on exactly the chosen scope; listings through that key also come back
clamped to it (checked live on 2026-11-04: 2 attributes with the lab key,
173 with the admin key).

Elaboration needs an entity or `sweep: true`, and a sweep did not finish in
180 s even with budget 3, so each entity in the scope is elaborated in turn
(0.4 s each when tried live).

The whole Context (scope None) runs with the admin key itself, for counts and
consolidation only; the endpoint allows that only as a consolidation preview.
"""

import logging
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from surrealdb_memory import AsyncMemory

from app.adapters.agent_memory.scoped_keys import ScopedKeys
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_lab import LabCounts, LabOutcome

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_MAX_PAGES = 20
# Entity ids come back as "['organisation', 'harbor_freight_lines']".
_ENTITY_ID = re.compile(r"""\[\s*'([^']*)'\s*,\s*'(.*)'\s*\]""")


def _in_scope(record: dict[str, Any], scope: str) -> bool:
    """A record's scope is a list of clauses of paths with a trailing slash."""
    for clause in record.get("scope") or []:
        for path in clause if isinstance(clause, list) else [clause]:
            if str(path).strip("/") == scope:
                return True
    return False


def _entity_ref(record: dict[str, Any]) -> str | None:
    match = _ENTITY_ID.fullmatch(str(record.get("id", "")).strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _relation_line(raw: Any) -> str:
    if isinstance(raw, dict):
        parts = [raw.get("subject"), raw.get("label"), raw.get("object")]
        if all(parts):
            return " ".join(str(p).removeprefix("entity:") for p in parts)
        return str(raw.get("summary") or raw)
    return str(raw)


class AgentMemoryLab:
    def __init__(
        self,
        admin: AsyncMemory,
        connect: Callable[[str], AsyncMemory],
        *,
        whole: AsyncMemory | None = None,
    ) -> None:
        """`whole`: an admin-key client for whole-Context runs, owned (and closed) here.

        Pooling every scope outlasts the shared admin client's timeout (a
        whole-Context consolidation preview took over 30 s live), so the
        composition root passes a client with a longer one.
        """
        self._admin = admin
        self._whole = whole
        self._keys = ScopedKeys(admin, connect, prefix="membrain-lab")

    async def counts(self, scope: str | None) -> LabCounts:
        client = await self._client(scope)
        entities = await self._all(client, "entities")
        attributes = await self._all(client, "attributes")
        relations = await self._all(client, "relations")
        if scope is not None:
            attributes = [a for a in attributes if _in_scope(a, scope)]
            relations = [r for r in relations if _in_scope(r, scope)]
        sources = Counter(
            str((r.get("source") or {}).get("kind") or "unknown") for r in attributes + relations
        )
        return LabCounts(
            entities=len(entities),
            attributes=len(attributes),
            relations=len(relations),
            by_source=dict(sources),
        )

    async def consolidate(self, scope: str | None, *, dry_run: bool) -> LabOutcome:
        raw = await self._post(scope, "consolidate", {"dryRun": dry_run})
        items = []
        for o in raw.get("outcomes") or []:
            line = (
                f"{o.get('kind')} · {o.get('entityName')} · {o.get('key')} = {o.get('value')}"
                f" (proof {o.get('proofCount', 0)})"
            )
            if o.get("rationale"):
                line += f" · {o['rationale']}"
            items.append(line)
        return LabOutcome(
            summary={k: int(raw.get(k) or 0) for k in ("created", "updated", "superseded")},
            items=items,
            trace_ids=[raw["traceId"]] if raw.get("traceId") else [],
        )

    async def elaborate(self, scope: str, *, dry_run: bool) -> LabOutcome:
        client = await self._client(scope)
        refs = [ref for ref in map(_entity_ref, await self._all(client, "entities")) if ref]
        emitted = 0
        items: list[str] = []
        traces: list[str] = []
        for ref in refs:
            raw = await self._post(scope, "elaborate", {"entityRef": ref, "dryRun": dry_run})
            emitted += int(raw.get("relationsEmitted") or 0)
            for outcome in raw.get("outcomes") or []:
                items += [_relation_line(p) for p in outcome.get("proposedRelations") or []]
                if outcome.get("traceId"):
                    traces.append(str(outcome["traceId"]))
        return LabOutcome(
            summary={"entities": len(refs), "relations": emitted}, items=items, trace_ids=traces
        )

    async def reflect(self, scope: str, query: str, *, persist: bool) -> LabOutcome:
        raw = await self._post(scope, "reflect", {"query": query, "persist": persist})
        evidence = [str(e) for e in raw.get("evidence") or []]
        saved = [
            str(a.get("summary") or f"{a.get('key')} = {a.get('value')}")
            if isinstance(a, dict)
            else str(a)
            for a in raw.get("persistedAttributes") or []
        ]
        return LabOutcome(
            summary={"evidence": len(evidence), "saved": len(saved)},
            items=[f"evidence: {e}" for e in evidence] + [f"saved: {s}" for s in saved],
            text=raw.get("reflection") or None,
            trace_ids=[raw["traceId"]] if raw.get("traceId") else [],
        )

    async def close(self) -> None:
        await self._keys.close()
        if self._whole is not None:
            await self._whole.close()

    async def _client(self, scope: str | None) -> AsyncMemory:
        """The admin client for the whole Context, else a key clamped to `scope`."""
        if scope is None:
            return self._whole or self._admin
        return await self._keys.client_for(scope, {"memory:read": [scope], "memory:write": [scope]})

    async def _post(self, scope: str | None, op: str, body: dict[str, Any]) -> dict[str, Any]:
        client = await self._client(scope)
        try:
            raw: dict[str, Any] = await client._transport.request(
                "POST", f"{client._base}/{op}", json=body
            )
        except Exception as exc:
            raise self._failed(op, exc) from exc
        return raw

    async def _all(self, client: AsyncMemory, kind: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": _PAGE_SIZE}
        try:
            for _ in range(_MAX_PAGES):
                page: Any = await client._transport.request(
                    "GET", f"{client._base}/{kind}", params=params
                )
                items.extend(page.get(kind, []))
                more = page.get("page") or {}
                if not (more.get("hasMore") and more.get("nextCursor")):
                    break
                params = {"limit": _PAGE_SIZE, "cursor": more["nextCursor"]}
        except Exception as exc:
            raise self._failed(f"list {kind}", exc) from exc
        return items

    @staticmethod
    def _failed(op: str, exc: Exception) -> MemoryUnavailableError:
        logger.warning("Agent Memory lab %s failed", op, exc_info=True)
        return MemoryUnavailableError(str(exc))


class NotConfiguredLab:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def counts(self, scope: str | None) -> LabCounts:
        raise MemoryNotConfiguredError

    async def consolidate(self, scope: str | None, *, dry_run: bool) -> LabOutcome:
        raise MemoryNotConfiguredError

    async def elaborate(self, scope: str, *, dry_run: bool) -> LabOutcome:
        raise MemoryNotConfiguredError

    async def reflect(self, scope: str, query: str, *, persist: bool) -> LabOutcome:
        raise MemoryNotConfiguredError

    async def close(self) -> None:
        return None
