"""MemoryBrain adapters for SurrealDB Agent Memory."""

import asyncio
import logging
import re
from typing import Any

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_brain import (
    BrainEntity,
    BrainFact,
    BrainRelation,
    BrainSnapshot,
    BrainSource,
)

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
# A stop for a cursor that never ends: far beyond this context's size.
_MAX_PAGES = 100
# Entity ids come back as "['concept', 'tier_a_products']".
_ENTITY_ID = re.compile(r"""\[\s*'([^']*)'\s*,\s*'(.*)'\s*\]""")


class AgentMemoryBrain:
    """Pages through GET /entities, /attributes and /relations with the admin key.

    The listings take no scope filter (Agent Memory ignores one), so callers
    filter by the `scope` each fact and relation carries.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client
        self._base = client.entities._base.rsplit("/entities", 1)[0]

    async def snapshot(self) -> BrainSnapshot:
        entities, facts, relations = await asyncio.gather(
            self._all("entities"), self._all("attributes"), self._all("relations")
        )
        return BrainSnapshot(
            entities=[e for e in map(_entity, entities) if e],
            facts=[_fact(a) for a in facts],
            relations=[_relation(r) for r in relations],
        )

    async def _all(self, kind: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": _PAGE_SIZE}
        try:
            for _ in range(_MAX_PAGES):
                page: Any = await self._client.entities._transport.request(
                    "GET", f"{self._base}/{kind}", params=params
                )
                items.extend(page.get(kind, []))
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
