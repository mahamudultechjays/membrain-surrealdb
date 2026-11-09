"""Capture flow: preview an extraction as reviewable facts, then store what was kept.

Preview runs Agent Memory's dry run and remembers the result here (in process,
no persistence) under a preview id. Store then either re-runs full extraction
on the source text (mode "full") or writes only the kept facts as triples
(mode "triples"). The mode names match Agent Memory's `infer` values.

Agent Memory gives no per-fact confidence and, in previews, no link from an
attribute to its entity. So the preview counts facts with an uncertainty note
instead, and an attribute whose entity can't be told apart is shown but can only
be stored with mode full.
"""

import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.fact_tags import FactTagRepository
from app.domain.ports.memory_capture import (
    CaptureResult,
    ExtractedAttribute,
    FactTriple,
    MemoryCapture,
)

logger = logging.getLogger(__name__)

StoreMode = Literal["triples", "full"]

# Documents longer than this are previewed from their first PREVIEW_WORDS only.
LARGE_DOCUMENT_WORDS = 2000
PREVIEW_WORDS = 500
TRUNCATED_REASON = f"Large document: preview shows first {PREVIEW_WORDS} words only"

MAX_PREVIEWS = 200
CATEGORIES = frozenset({"identity", "knowledge", "context"})
NO_ENTITY_NOTE = "entity not known in preview; store with mode full"


class CaptureFlowError(Exception):
    """The request can't be served as asked; the message says why."""


@dataclass(frozen=True, slots=True)
class ReviewFact:
    id: str
    fact: str
    type: str
    source: str
    note: str | None = None
    # What gets written with mode triples; None when the fact can't be a triple.
    triple: FactTriple | None = None
    # An attribute Agent Memory gave no entity for (key, value, category): the
    # user can pick its entity, which turns it into a triple at store time.
    unlinked: tuple[str, str, str] | None = None


@dataclass(frozen=True, slots=True)
class EntityChoice:
    name: str
    entity_type: str


@dataclass(frozen=True, slots=True)
class Preview:
    id: str
    # Email of the user who ran it; only they can store from it.
    owner: str
    scope: str
    text: str
    facts: list[ReviewFact]
    corrections: list[str] = field(default_factory=list)
    truncated: bool = False
    doc_id: str | None = None
    # Entities the preview found; the choices offered for an unlinked fact.
    entities: list[EntityChoice] = field(default_factory=list)

    @property
    def uncertain(self) -> int:
        """Facts Agent Memory raised an uncertainty about."""
        return sum(1 for f in self.facts if (f.note or "").startswith("uncertain"))


@dataclass(frozen=True, slots=True)
class CreatedFact:
    entity: str
    key: str
    value: str
    id: str | None


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    fact_id: str | None
    key: str | None
    old_value: str | None
    new_value: str | None
    changed_at: str


@dataclass(frozen=True, slots=True)
class StoreOutcome:
    stored_id: str
    written: int
    created_facts: list[CreatedFact]
    history: list[HistoryEntry]


class PreviewCache:
    """The most recent previews, oldest dropped first."""

    def __init__(self, limit: int = MAX_PREVIEWS) -> None:
        self._limit = limit
        self._previews: OrderedDict[str, Preview] = OrderedDict()
        # Documents uploaded by a direct extract (no preview): doc id -> owner.
        self._documents: OrderedDict[str, str] = OrderedDict()

    def put(self, preview: Preview) -> None:
        self._previews[preview.id] = preview
        while len(self._previews) > self._limit:
            self._previews.popitem(last=False)

    def get(self, preview_id: str) -> Preview | None:
        return self._previews.get(preview_id)

    def remember_document(self, doc_id: str, owner: str) -> None:
        """Record who uploaded a document outside a preview."""
        self._documents[doc_id] = owner
        while len(self._documents) > self._limit:
            self._documents.popitem(last=False)

    def owner_of_document(self, doc_id: str) -> str | None:
        """Who uploaded this document, while it is still cached."""
        from_preview = (p.owner for p in self._previews.values() if p.doc_id == doc_id)
        return next(from_preview, None) or self._documents.get(doc_id)


def shorten_document(text: str) -> tuple[str, bool]:
    """The first PREVIEW_WORDS words of a large document, and whether it was cut."""
    words = text.split()
    if len(words) <= LARGE_DOCUMENT_WORDS:
        return text, False
    return " ".join(words[:PREVIEW_WORDS]), True


async def preview(
    capture: MemoryCapture,
    *,
    owner: str,
    scope: str,
    text: str,
    source: str,
    truncated: bool = False,
    doc_id: str | None = None,
) -> Preview:
    result = await capture.preview(text, scope)
    return Preview(
        id=f"prev_{uuid.uuid4().hex[:12]}",
        owner=owner,
        scope=scope,
        text=text,
        facts=review_facts(result, source=source),
        corrections=list(result.corrections),
        truncated=truncated,
        doc_id=doc_id,
        entities=[EntityChoice(e.name, e.entity_type) for e in result.entities],
    )


def review_facts(result: CaptureResult, *, source: str) -> list[ReviewFact]:
    types = {e.name: e.entity_type for e in result.entities}
    only_entity = result.entities[0].name if len(result.entities) == 1 else None
    facts: list[ReviewFact] = []

    def add(
        text: str,
        category: str,
        triple: FactTriple | None,
        note: str | None,
        unlinked: tuple[str, str, str] | None = None,
    ) -> None:
        facts.append(
            ReviewFact(f"e{len(facts) + 1}", text, category, source, note, triple, unlinked)
        )

    described: set[str] = set()
    for a in result.attributes:
        entity = a.entity or only_entity
        triple = _triple(entity, types, a.key, a.value, a.memory_category) if entity else None
        add(
            f"{entity or '?'} · {a.key} = {a.value}",
            a.memory_category,
            triple,
            None if entity else NO_ENTITY_NOTE,
            None if entity else (a.key, a.value, a.memory_category),
        )
        if entity:
            described.add(entity)
    for r in result.relations:
        triple = _triple(r.subject, types, r.label, r.object, r.memory_category)
        add(f"{r.subject} · {r.label} → {r.object}", r.memory_category, triple, None)
        described.update({r.subject, r.object})
    for e in result.entities:
        if e.name not in described:
            triple = _triple(e.name, types, "type", e.entity_type, e.memory_category)
            add(f"{e.name} · type = {e.entity_type}", e.memory_category, triple, None)

    return [_with_uncertainty(f, result) for f in facts]


async def store(
    capture: MemoryCapture,
    stored: Preview,
    *,
    kept: list[str],
    mode: StoreMode,
    memory_category: str | None,
    entity_choices: dict[str, str] | None = None,
    links: FactTagRepository | None = None,
) -> StoreOutcome:
    """Mode triples writes the kept facts as they are, then the original text as
    a passage (no extraction), so a VCT value filter can keep the text's chunk
    when its facts match; `links` records which facts came from that text."""
    by_id = {f.id: f for f in stored.facts}
    unknown = [fact_id for fact_id in kept if fact_id not in by_id]
    if unknown:
        raise CaptureFlowError(f"Unknown fact ids for this preview: {', '.join(unknown)}")
    linked = _link_entities(stored, entity_choices or {})

    if mode == "full":
        return await extract(capture, scope=stored.scope, text=stored.text, links=links)

    triples = [
        _recategorised(triple, memory_category)
        for triple in (by_id[fact_id].triple or linked.get(fact_id) for fact_id in kept)
        if triple is not None
    ]
    if not triples:
        raise CaptureFlowError("None of the kept facts can be stored as triples; use mode full.")
    result = await capture.store_facts(triples, stored.scope)
    turn = await _store_passage(capture, stored.text, stored.scope)
    await _link(links, result, turn, stored.scope)
    return _outcome(result, len(triples), triples)


async def _store_passage(capture: MemoryCapture, text: str, scope: str) -> str | None:
    """Best effort: the facts are already saved, so a failure here only loses
    the link from the text's chunk to them."""
    if not text.strip():
        return None
    try:
        return await capture.store_passage(text, scope)
    except (MemoryNotConfiguredError, MemoryUnavailableError):
        logger.warning("Storing the captured text as a passage failed", exc_info=True)
        return None


async def _link(
    links: FactTagRepository | None, result: CaptureResult, turn: str | None, scope: str
) -> None:
    ids = [a.id for a in result.attributes if a.id]
    if links is not None and turn and ids:
        await links.link_turns([(fact_id, turn, scope) for fact_id in ids])


async def extract(
    capture: MemoryCapture, *, scope: str, text: str, links: FactTagRepository | None = None
) -> StoreOutcome:
    """Mode full with no preview: Agent Memory extracts from the text and saves all it finds.

    A preview would be thrown away here anyway, since full extraction runs the
    model again; skipping it saves one model run.
    """
    result = await capture.store(text, scope)
    await _link(links, result, result.turn_id, scope)
    return _outcome(result, len(result.attributes) + len(result.relations), [])


def _outcome(result: CaptureResult, written: int, triples: list[FactTriple]) -> StoreOutcome:
    created = [_created(a) for a in result.attributes if a.entity] or [
        CreatedFact(t.entity_name, t.key, t.value, None) for t in triples
    ]
    return StoreOutcome(
        stored_id=f"store_{uuid.uuid4().hex[:12]}",
        written=written,
        created_facts=created,
        history=[_history(c, created) for c in result.corrections],
    )


def _triple(entity: str, types: dict[str, str], key: str, value: str, category: str) -> FactTriple:
    return FactTriple(
        entity_name=entity,
        entity_type=types.get(entity) or "thing",
        key=key,
        value=value,
        memory_category=category if category in CATEGORIES else "knowledge",
    )


def _link_entities(stored: Preview, choices: dict[str, str]) -> dict[str, FactTriple]:
    """Triples for unlinked facts whose entity the user picked from the preview's entities."""
    by_id = {f.id: f for f in stored.facts}
    types = {e.name: e.entity_type for e in stored.entities}
    linked: dict[str, FactTriple] = {}
    for fact_id, entity in choices.items():
        fact = by_id.get(fact_id)
        if fact is None or fact.unlinked is None:
            raise CaptureFlowError(f"Fact {fact_id} does not need an entity choice")
        if entity not in types:
            raise CaptureFlowError(f"{entity!r} is not an entity found in this preview")
        key, value, category = fact.unlinked
        linked[fact_id] = _triple(entity, types, key, value, category)
    return linked


def _recategorised(triple: FactTriple, category: str | None) -> FactTriple:
    if category is None:
        return triple
    return FactTriple(triple.entity_name, triple.entity_type, triple.key, triple.value, category)


def _with_uncertainty(fact: ReviewFact, result: CaptureResult) -> ReviewFact:
    for u in result.uncertainties:
        if u.about and u.about.lower() in fact.fact.lower():
            note = f"uncertain: {u.reason}"
            return ReviewFact(fact.id, fact.fact, fact.type, fact.source, note, fact.triple)
    return fact


def _created(attribute: ExtractedAttribute) -> CreatedFact:
    return CreatedFact(attribute.entity or "", attribute.key, attribute.value, attribute.id)


def _history(correction: str, created: list[CreatedFact]) -> HistoryEntry:
    """Agent Memory's correction shape is undocumented; pick out what it carries."""
    try:
        raw = json.loads(correction)
    except ValueError:
        raw = None
    fields = raw if isinstance(raw, dict) else {}
    key = _opt(fields.get("key"))
    match = next((c for c in created if key and c.key == key), None)
    return HistoryEntry(
        fact_id=match.id if match else None,
        key=key,
        old_value=_opt(fields.get("from") or fields.get("old_value") or fields.get("oldValue")),
        new_value=_opt(fields.get("to") or fields.get("new_value") or fields.get("newValue"))
        or (match.value if match else None),
        changed_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def _opt(value: object) -> str | None:
    return None if value is None else str(value)
