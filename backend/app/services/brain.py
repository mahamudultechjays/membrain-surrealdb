"""Brain: what memory knows, one entity at a time, limited to the scopes asked for.

Agent Memory lists entities, facts and relations without any scope filter, so
the filter happens here, on the scope each fact and relation was written to. An
entity is shown when at least one of its facts or relations is in scope; its
type and display name come from the entity listing.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from app.domain.ports.memory_brain import (
    BrainAction,
    BrainFact,
    BrainRelation,
    BrainSnapshot,
    BrainTurn,
    BrainUnknown,
)


@dataclass(slots=True)
class EntityView:
    ref: str
    name: str
    entity_type: str
    category: str
    scopes: list[str] = field(default_factory=list)
    # The newest created_at among the entity's facts and relations shown.
    updated_at: str = ""
    facts: list[BrainFact] = field(default_factory=list)
    relations: list[BrainRelation] = field(default_factory=list)


@dataclass(slots=True)
class BrainView:
    entities: list[EntityView]
    # Every scope that holds something the caller may see, for the filter.
    scopes: list[str]
    # Display names for relation targets, by entity ref.
    names: dict[str, str]


class ScopeFilter:
    """Which written scopes count as "in".

    `allowed` is the caller's whole read region (None: everything, for admins).
    `wanted` narrows it; with `subscopes`, a wanted path also takes in the
    paths below it, but never past `allowed`.
    """

    def __init__(
        self, allowed: set[str] | None, wanted: set[str] | None, *, subscopes: bool
    ) -> None:
        self._allowed = allowed
        self._wanted = wanted
        self._subscopes = subscopes

    def visible(self, path: str) -> bool:
        return self._allowed is None or path in self._allowed

    def matches(self, scopes: tuple[str, ...]) -> bool:
        return any(self.visible(path) and self._wanted_path(path) for path in scopes)

    def _wanted_path(self, path: str) -> bool:
        if self._wanted is None:
            return True
        return any(
            path == want or (self._subscopes and path.startswith(want + "/"))
            for want in self._wanted
        )


def view(snapshot: BrainSnapshot, scope: ScopeFilter) -> BrainView:
    known = {entity.ref: entity for entity in snapshot.entities}
    names = {ref: entity.name for ref, entity in known.items()}
    grouped: dict[str, EntityView] = {}

    def entity_for(ref: str) -> EntityView:
        if ref not in grouped:
            entity = known.get(ref)
            entity_type, _, key = ref.partition("/")
            grouped[ref] = EntityView(
                ref=ref,
                name=entity.name if entity else _readable(key),
                entity_type=entity.entity_type if entity else entity_type,
                category=entity.category if entity else "",
            )
        return grouped[ref]

    def note(found: EntityView, scopes: tuple[str, ...], created_at: str) -> None:
        for path in scopes:
            if scope.visible(path) and path not in found.scopes:
                found.scopes.append(path)
        found.updated_at = max(found.updated_at, created_at)

    for fact in snapshot.facts:
        if fact.entity_ref and scope.matches(fact.scopes):
            found = entity_for(fact.entity_ref)
            found.facts.append(fact)
            note(found, fact.scopes, fact.created_at)
    for relation in snapshot.relations:
        if relation.subject_ref and scope.matches(relation.scopes):
            found = entity_for(relation.subject_ref)
            found.relations.append(relation)
            note(found, relation.scopes, relation.created_at)

    for found in grouped.values():
        found.facts.sort(key=lambda f: f.created_at, reverse=True)
        found.relations.sort(key=lambda r: r.created_at, reverse=True)
        found.scopes.sort()
        names.setdefault(found.ref, found.name)

    written: list[tuple[str, ...]] = [f.scopes for f in snapshot.facts]
    written += [r.scopes for r in snapshot.relations]
    every = {path for scopes in written for path in scopes if scope.visible(path)}
    return BrainView(
        entities=sorted(grouped.values(), key=lambda e: e.updated_at, reverse=True),
        scopes=sorted(every),
        names=names,
    )


@dataclass(slots=True)
class ChunkView:
    """A memory chunk: the text of one captured turn, as memory stored it."""

    id: str
    session_id: str
    role: str
    text: str
    created_at: str
    # Inferred: turns carry no scope, so these are the scopes of the facts and
    # relations taken from the turn (else from its session).
    scopes: list[str]
    # Ids of the facts and relations Agent Memory extracted from this turn.
    derived: list[str]


def sessions(snapshot: BrainSnapshot, scope: ScopeFilter) -> list[str]:
    """The sessions that facts and relations in scope came from, once each."""
    found: dict[str, None] = {}
    for record in _records(snapshot):
        if record.source.session_id and scope.matches(record.scopes):
            found[record.source.session_id] = None
    return list(found)


def chunks(
    snapshot: BrainSnapshot, turns: Iterable[BrainTurn], scope: ScopeFilter
) -> list[ChunkView]:
    """Turns in scope, newest first, each with the records extracted from it."""
    by_turn: dict[str, list[BrainFact | BrainRelation]] = {}
    by_session: dict[str, list[BrainFact | BrainRelation]] = {}
    for record in _records(snapshot):
        ref = record.source.ref or ""
        if ref.startswith("turn:"):
            by_turn.setdefault(ref.removeprefix("turn:"), []).append(record)
        if record.source.session_id:
            by_session.setdefault(record.source.session_id, []).append(record)

    shown: list[ChunkView] = []
    for turn in turns:
        derived = by_turn.get(turn.id, [])
        written = derived or by_session.get(turn.session_id, [])
        paths = tuple(dict.fromkeys(path for r in written for path in r.scopes))
        if not turn.content.strip() or not scope.matches(paths):
            continue
        shown.append(
            ChunkView(
                id=turn.id,
                session_id=turn.session_id,
                role=turn.role,
                text=turn.content,
                created_at=turn.created_at,
                scopes=sorted(p for p in paths if scope.visible(p)),
                derived=[r.id for r in derived],
            )
        )
    return sorted(shown, key=lambda c: c.created_at, reverse=True)


def _records(snapshot: BrainSnapshot) -> list[BrainFact | BrainRelation]:
    return [*snapshot.facts, *snapshot.relations]


@dataclass(slots=True)
class ActionView:
    action: BrainAction
    actor_name: str
    # The object entity's name, or the action's free-text object.
    object_name: str | None
    # Inferred: actions carry no scope, so these come from the facts and
    # relations taken from the same turn (else the same session).
    scopes: list[str]


def actions(snapshot: BrainSnapshot, scope: ScopeFilter, names: dict[str, str]) -> list[ActionView]:
    """Actions in scope, newest first, with their scope inferred from their capture."""
    by_turn: dict[str, set[str]] = {}
    by_session: dict[str, set[str]] = {}
    for record in _records(snapshot):
        if (record.source.ref or "").startswith("turn:"):
            by_turn.setdefault(record.source.ref or "", set()).update(record.scopes)
        if record.source.session_id:
            by_session.setdefault(record.source.session_id, set()).update(record.scopes)

    def name(ref: str) -> str:
        return names.get(ref) or _readable(ref.partition("/")[2])

    shown: list[ActionView] = []
    for action in snapshot.actions:
        paths = by_turn.get(action.source.ref or "") or by_session.get(
            action.source.session_id or "", set()
        )
        if not scope.matches(tuple(paths)):
            continue
        shown.append(
            ActionView(
                action=action,
                actor_name=name(action.actor_ref),
                object_name=name(action.object_ref) if action.object_ref else action.object_text,
                scopes=sorted(p for p in paths if scope.visible(p)),
            )
        )
    return sorted(shown, key=lambda a: a.action.created_at, reverse=True)


def unknowns(snapshot: BrainSnapshot, scope: ScopeFilter) -> list[BrainUnknown]:
    """Open questions and contradictions in scope, newest first."""
    found = [u for u in snapshot.unknowns if scope.matches(u.scopes)]
    return sorted(found, key=lambda u: u.created_at, reverse=True)


def entities_in(snapshot: BrainSnapshot, scope: ScopeFilter) -> list[str]:
    """The entities with a fact in scope: the ones whose history may hold replaced values."""
    found: dict[str, None] = {}
    for fact in snapshot.facts:
        if fact.entity_ref and scope.matches(fact.scopes):
            found[fact.entity_ref] = None
    return list(found)


def with_replaced(snapshot: BrainSnapshot, replaced: Iterable[BrainFact]) -> BrainSnapshot:
    """The snapshot with replaced facts (from entity histories) added, once each."""
    known = {fact.id for fact in snapshot.facts}
    extra = [fact for fact in replaced if fact.id not in known]
    return replace(snapshot, facts=[*snapshot.facts, *extra]) if extra else snapshot


def _readable(key: str) -> str:
    """A fallback name from an entity key: 'tier_a_products' -> 'tier a products'.

    Agent Memory files "I ..." statements under the speaker's principal
    (person/principal:<id>), which its summaries call "self".
    """
    if key.startswith("principal:"):
        return "self"
    return key.replace("_", " ") or "unknown"
