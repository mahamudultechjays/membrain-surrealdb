"""Brain: what memory knows, one entity at a time, limited to the scopes asked for.

Agent Memory lists entities, facts and relations without any scope filter, so
the filter happens here, on the scope each fact and relation was written to. An
entity is shown when at least one of its facts or relations is in scope; its
type and display name come from the entity listing.
"""

from dataclasses import dataclass, field

from app.domain.ports.memory_brain import BrainFact, BrainRelation, BrainSnapshot


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


def _readable(key: str) -> str:
    """A fallback name from an entity key: 'tier_a_products' -> 'tier a products'.

    Agent Memory files "I ..." statements under the speaker's principal
    (person/principal:<id>), which its summaries call "self".
    """
    if key.startswith("principal:"):
        return "self"
    return key.replace("_", " ") or "unknown"
