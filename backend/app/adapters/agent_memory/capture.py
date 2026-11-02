"""MemoryCapture adapters for SurrealDB Agent Memory."""

import json
import logging
from typing import Any

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_capture import (
    CaptureMode,
    CaptureResult,
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedInstruction,
    ExtractedRelation,
    ExtractedUncertainty,
    FactTriple,
)

logger = logging.getLogger(__name__)


class AgentMemoryCapture:
    """Sends text to `POST /facts` and maps the extraction summary.

    Preview uses `infer: "preview"`, the documented dry run: extraction runs
    and nothing is saved. Store uses `infer: "full"`, which extracts again
    (a second model run, so the result can differ from the preview) and saves.
    Store facts uses `infer: "triples"`: the given facts are saved as they are.
    A scope, when given, is sent as the write region (`scopes`).
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def preview(self, text: str, scope: str | None = None) -> CaptureResult:
        return await self._remember(text, scope, infer="preview", mode="preview")

    async def store(self, text: str, scope: str | None = None) -> CaptureResult:
        return await self._remember(text, scope, infer="full", mode="stored")

    async def store_facts(self, facts: list[FactTriple], scope: str) -> CaptureResult:
        triples = [
            {
                "entity": {"type": f.entity_type, "name": f.entity_name},
                "key": f.key,
                "value": f.value,
                "memory_category": f.memory_category,
            }
            for f in facts
        ]
        return await self._call("triples", "stored", text=None, scopes=[scope], triples=triples)

    async def _remember(
        self, text: str, scope: str | None, *, infer: str, mode: CaptureMode
    ) -> CaptureResult:
        return await self._call(infer, mode, text=text, scopes=[scope] if scope else None)

    async def _call(
        self,
        infer: str,
        mode: CaptureMode,
        *,
        text: str | None,
        scopes: list[str] | None,
        triples: list[dict[str, Any]] | None = None,
    ) -> CaptureResult:
        try:
            response = await self._client.remember(
                text, infer=infer, scopes=scopes, triples=triples
            )
        except Exception as exc:
            logger.warning("Agent Memory remember (%s) failed", infer, exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc

        extraction = response.extraction
        if extraction is None:
            return CaptureResult(mode=mode, session_id=response.session_id)

        names = {e.get("id"): e.get("name", "") for e in extraction.entities if e.get("id")}
        return CaptureResult(
            mode=mode,
            session_id=response.session_id,
            turn_id=response.turn_id or extraction.turn_id or None,
            entities=[_entity(e) for e in extraction.entities],
            attributes=[_attribute(a, names) for a in extraction.attributes],
            relations=[_relation(r) for r in extraction.relations],
            instructions=[_instruction(i) for i in extraction.instructions],
            uncertainties=[_uncertainty(u) for u in extraction.uncertainties],
            corrections=[_text(c) for c in extraction.corrections],
        )


class NotConfiguredCapture:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def preview(self, text: str, scope: str | None = None) -> CaptureResult:
        raise MemoryNotConfiguredError

    async def store(self, text: str, scope: str | None = None) -> CaptureResult:
        raise MemoryNotConfiguredError

    async def store_facts(self, facts: list[FactTriple], scope: str) -> CaptureResult:
        raise MemoryNotConfiguredError


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _entity(raw: dict[str, Any]) -> ExtractedEntity:
    is_new = raw.get("isNew")
    return ExtractedEntity(
        name=_str(raw.get("name")),
        entity_type=_str(raw.get("entityType")),
        memory_category=_str(raw.get("memoryCategory")),
        is_new=is_new if isinstance(is_new, bool) else None,
    )


def _attribute(raw: dict[str, Any], names: dict[Any, str]) -> ExtractedAttribute:
    return ExtractedAttribute(
        key=_str(raw.get("key")),
        value=_str(raw.get("value")),
        memory_category=_str(raw.get("memoryCategory")),
        entity=names.get(raw.get("entityId")) or None,
        id=_str(raw.get("id")) or None,
    )


def _relation(raw: dict[str, Any]) -> ExtractedRelation:
    return ExtractedRelation(
        subject=_str(raw.get("subject")),
        label=_str(raw.get("label")),
        object=_str(raw.get("object")),
        memory_category=_str(raw.get("memoryCategory")),
    )


def _instruction(raw: dict[str, Any]) -> ExtractedInstruction:
    return ExtractedInstruction(
        label=_str(raw.get("label")), description=_str(raw.get("description"))
    )


def _uncertainty(raw: dict[str, Any]) -> ExtractedUncertainty:
    return ExtractedUncertainty(about=_str(raw.get("about")), reason=_str(raw.get("reason")))
