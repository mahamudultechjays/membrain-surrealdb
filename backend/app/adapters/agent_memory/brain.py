"""MemoryBrain adapters for SurrealDB Agent Memory."""

import asyncio
import logging
import re
import time
from collections.abc import Collection
from typing import Any
from urllib.parse import quote

from surrealdb_memory import AsyncMemory, MemoryNotFoundError

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_brain import (
    BrainAction,
    BrainEntity,
    BrainFact,
    BrainRelation,
    BrainReplaced,
    BrainSnapshot,
    BrainSource,
    BrainTurn,
    BrainTurns,
    BrainUnknown,
)

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
# A stop for a cursor that never ends: far beyond this context's size.
_MAX_PAGES = 100
# Entity ids come back as "['concept', 'tier_a_products']".
_ENTITY_ID = re.compile(r"""\[\s*'([^']*)'\s*,\s*'(.*)'\s*\]""")
# Turns are read one session at a time (about a second each), so in parallel,
# and kept briefly: a captured turn never changes, only chat sessions grow.
_TURN_CONCURRENCY = 16
_TURN_PAGE_SIZE = 200
_TURN_TTL_SECONDS = 120.0


class AgentMemoryBrain:
    """Pages through GET /entities, /attributes and /relations with the admin key.

    The listings take no scope filter (Agent Memory ignores one), so callers
    filter by the `scope` each fact and relation carries. Memory chunks have no
    listing at all; they are read as the turns of each session a fact names.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client
        self._base = client.entities._base.rsplit("/entities", 1)[0]
        # session id -> (when read, its turns)
        self._turns: dict[str, tuple[float, tuple[BrainTurn, ...]]] = {}
        # entity ref -> (when read, its replaced facts)
        self._history: dict[str, tuple[float, tuple[BrainFact, ...]]] = {}

    async def replaced(self, entity_refs: Collection[str]) -> BrainReplaced:
        wanted = [r for r in dict.fromkeys(entity_refs) if "/" in r]
        now = time.monotonic()
        stale = [
            r
            for r in wanted
            if r not in self._history or now - self._history[r][0] > _TURN_TTL_SECONDS
        ]
        gate = asyncio.Semaphore(_TURN_CONCURRENCY)

        async def read(ref: str) -> None:
            entity_type, _, name = ref.partition("/")
            entity = f"{quote(entity_type, safe='')}/{quote(name, safe='')}"
            path = f"{self._base}/entities/{entity}/history"
            async with gate:
                try:
                    body: Any = await self._client.entities._transport.request("GET", path)
                    found = tuple(
                        _fact(raw)
                        for raw in (body.get("history", []) if isinstance(body, dict) else [])
                        if raw.get("supersededBy")
                    )
                except MemoryNotFoundError:
                    found = ()
                except Exception:
                    logger.warning("Agent Memory history for %s failed", ref, exc_info=True)
                    return
            self._history[ref] = (now, found)

        await asyncio.gather(*(read(r) for r in stale))
        return BrainReplaced(
            facts=[fact for r in wanted if r in self._history for fact in self._history[r][1]],
            missing=sum(1 for r in wanted if r not in self._history),
        )

    async def turns(self, session_ids: Collection[str]) -> BrainTurns:
        wanted = [s for s in dict.fromkeys(session_ids) if s]
        now = time.monotonic()
        stale = [
            s for s in wanted if s not in self._turns or now - self._turns[s][0] > _TURN_TTL_SECONDS
        ]
        gate = asyncio.Semaphore(_TURN_CONCURRENCY)

        async def read(session_id: str) -> None:
            async with gate:
                try:
                    found = await self._session_turns(session_id)
                except MemoryNotFoundError:
                    found = ()
                except Exception:
                    # Keep what was read before, if anything; otherwise it is missing.
                    logger.warning("Agent Memory turns for %s failed", session_id, exc_info=True)
                    return
            self._turns[session_id] = (now, found)

        await asyncio.gather(*(read(s) for s in stale))
        return BrainTurns(
            turns=[turn for s in wanted if s in self._turns for turn in self._turns[s][1]],
            missing=sum(1 for s in wanted if s not in self._turns),
        )

    async def _session_turns(self, session_id: str) -> tuple[BrainTurn, ...]:
        path = f"{self._base}/sessions/{quote(session_id, safe='')}/turns"
        items: list[dict[str, Any]] = []
        for _ in range(_MAX_PAGES):
            page: Any = await self._client.entities._transport.request(
                "GET", path, params={"limit": _TURN_PAGE_SIZE, "offset": len(items)}
            )
            batch = page.get("turns", []) if isinstance(page, dict) else []
            items.extend(batch)
            if not (batch and (page.get("page") or {}).get("hasMore")):
                break
        return tuple(_turn(raw, session_id) for raw in items)

    async def snapshot(self) -> BrainSnapshot:
        entities, facts, relations, actions, unknowns = await asyncio.gather(
            self._all("entities"),
            self._all("attributes"),
            self._all("relations"),
            self._optional("actions", "actions"),
            self._optional("uncertainty", "unknowns"),
        )
        return BrainSnapshot(
            entities=[e for e in map(_entity, entities) if e],
            facts=[_fact(a) for a in facts],
            relations=[_relation(r) for r in relations],
            actions=[_action(a) for a in actions],
            unknowns=[_unknown(u) for u in unknowns],
        )

    async def _optional(self, path: str, key: str) -> list[dict[str, Any]]:
        """A listing the page can do without: on failure, nothing rather than an error."""
        try:
            return await self._all(path, key)
        except MemoryUnavailableError:
            return []

    async def _all(self, kind: str, key: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": _PAGE_SIZE}
        try:
            for _ in range(_MAX_PAGES):
                page: Any = await self._client.entities._transport.request(
                    "GET", f"{self._base}/{kind}", params=params
                )
                items.extend(page.get(key or kind, []))
                more = page.get("page") or {}
                if not (more.get("hasMore") and more.get("nextCursor")):
                    break
                params = {"limit": _PAGE_SIZE, "cursor": more["nextCursor"]}
        except Exception as exc:
            logger.warning("Agent Memory %s listing failed", kind, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        return items


class NotConfiguredBrain:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def snapshot(self) -> BrainSnapshot:
        raise MemoryNotConfiguredError

    async def turns(self, session_ids: Collection[str]) -> BrainTurns:
        raise MemoryNotConfiguredError

    async def replaced(self, entity_refs: Collection[str]) -> BrainReplaced:
        raise MemoryNotConfiguredError


def _turn(raw: dict[str, Any], session_id: str) -> BrainTurn:
    seq = raw.get("seq")
    return BrainTurn(
        id=str(raw.get("id", "")).removeprefix("turn:"),
        session_id=str(raw.get("session") or session_id).removeprefix("session:"),
        role=str(raw.get("role") or ""),
        content=str(raw.get("content") or ""),
        created_at=str(raw.get("createdAt") or ""),
        seq=seq if isinstance(seq, int) else 0,
    )


def _ref(raw: Any) -> str:
    """'entity:concept/tier_a_products' -> 'concept/tier_a_products'."""
    return str(raw or "").removeprefix("entity:")


def _scopes(raw: Any) -> tuple[str, ...]:
    """[['org/a/'], ['org/b/']] -> ('org/a', 'org/b'): every path, once."""
    paths: list[str] = []
    for clause in raw or []:
        for path in clause if isinstance(clause, list) else [clause]:
            clean = str(path).strip("/")
            if clean and clean not in paths:
                paths.append(clean)
    return tuple(paths)


def _text(raw: Any) -> str | None:
    """A non-empty string, or None."""
    text = str(raw).strip() if raw is not None else ""
    return text or None


def _number(raw: Any) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _source(raw: Any) -> BrainSource:
    if not isinstance(raw, dict):
        return BrainSource()
    return BrainSource(
        kind=_text(raw.get("kind")),
        ref=_text(raw.get("ref")),
        session_id=_text(raw.get("sessionId")),
        trust=_number(raw.get("trust")),
    )


def _labels(raw: Any) -> tuple[str, ...]:
    """Labels as "key=value" strings, whether sent as strings or as {key: value}."""
    labels: list[str] = []
    for label in raw or []:
        if isinstance(label, dict):
            labels += [f"{k}={v}" for k, v in label.items()]
        elif str(label).strip():
            labels.append(str(label).strip())
    return tuple(labels)


def _entity(raw: dict[str, Any]) -> BrainEntity | None:
    match = _ENTITY_ID.fullmatch(str(raw.get("id", "")).strip())
    entity_type = str(raw.get("entityType") or (match.group(1) if match else ""))
    if not match or not entity_type:
        return None
    return BrainEntity(
        ref=f"{match.group(1)}/{match.group(2)}",
        name=str(raw.get("name") or match.group(2)),
        entity_type=entity_type,
        category=str(raw.get("memoryCategory") or ""),
    )


def _fact(raw: dict[str, Any]) -> BrainFact:
    return BrainFact(
        id=str(raw.get("id", "")),
        entity_ref=_ref(raw.get("entity")),
        key=str(raw.get("key", "")),
        value=str(raw.get("value", "")),
        category=str(raw.get("memoryCategory") or ""),
        scopes=_scopes(raw.get("scope")),
        created_at=str(raw.get("createdAt") or ""),
        superseded_by=raw.get("supersededBy") or None,
        summary=_text(raw.get("summary")),
        labels=_labels(raw.get("labels")),
        confidence=_number(raw.get("confidence")),
        importance=_number(raw.get("importance")),
        supersedes=_text(raw.get("supersedes")),
        valid_from=_text(raw.get("validFrom")),
        valid_until=_text(raw.get("validUntil")),
        source=_source(raw.get("source")),
    )


def _relation(raw: dict[str, Any]) -> BrainRelation:
    return BrainRelation(
        id=str(raw.get("id", "")),
        subject_ref=_ref(raw.get("subject")),
        label=str(raw.get("label", "")),
        object_ref=_ref(raw.get("object")),
        category=str(raw.get("memoryCategory") or ""),
        scopes=_scopes(raw.get("scope")),
        created_at=str(raw.get("createdAt") or ""),
        summary=_text(raw.get("summary")),
        labels=_labels(raw.get("labels")),
        confidence=_number(raw.get("confidence")),
        valid_from=_text(raw.get("validFrom")),
        valid_until=_text(raw.get("validUntil")),
        source=_source(raw.get("source")),
    )


def _action(raw: dict[str, Any]) -> BrainAction:
    return BrainAction(
        id=str(raw.get("id", "")),
        actor_ref=_ref(raw.get("actor")),
        verb=str(raw.get("verb") or ""),
        object_ref=_ref(raw.get("object")) or None,
        object_text=_text(raw.get("objectText")),
        summary=_text(raw.get("summary")),
        category=str(raw.get("memoryCategory") or ""),
        created_at=str(raw.get("createdAt") or ""),
        occurred_at=_text(raw.get("occurredAt")),
        confidence=_number(raw.get("confidence")),
        source=_source(raw.get("source")),
    )


def _unknown(raw: dict[str, Any]) -> BrainUnknown:
    return BrainUnknown(
        id=str(raw.get("id", "")),
        about=str(raw.get("about") or ""),
        reason=str(raw.get("reason") or ""),
        resolved=bool(raw.get("resolved")),
        resolvable=bool(raw.get("resolvable")),
        scopes=_scopes(raw.get("scope")),
        created_at=str(raw.get("createdAt") or ""),
        entity_ref=_ref(raw.get("entity")) or None,
        key=_text(raw.get("key")),
        labels=_labels(raw.get("labels")),
    )
