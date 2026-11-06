"""Port for reading everything memory holds: entities, their facts and relations.

Facts and relations carry the scope they were written to; entities do not, so
an entity belongs to the scopes its facts and relations were written in.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BrainEntity:
    # "concept/tier_a_products": the type and key facts refer to it by.
    ref: str
    name: str
    entity_type: str
    category: str


@dataclass(frozen=True, slots=True)
class BrainSource:
    """Where a fact came from: e.g. kind "turn" (a captured input) or
    "elaboration" (inferred while processing one)."""

    kind: str | None = None
    ref: str | None = None
    session_id: str | None = None
    trust: float | None = None


@dataclass(frozen=True, slots=True)
class BrainFact:
    id: str
    entity_ref: str
    key: str
    value: str
    category: str
    scopes: tuple[str, ...]
    created_at: str
    # Set when a newer value replaced this one.
    superseded_by: str | None = None
    # Agent Memory's one-sentence version of the fact; None when it has none.
    summary: str | None = None
    # Descriptive tags, e.g. "source=email"; empty when it has none.
    labels: tuple[str, ...] = ()
    confidence: float | None = None
    importance: float | None = None
    # The older fact this one replaced.
    supersedes: str | None = None
    # When the fact holds true, if Agent Memory knows.
    valid_from: str | None = None
    valid_until: str | None = None
    source: BrainSource = BrainSource()


@dataclass(frozen=True, slots=True)
class BrainRelation:
    id: str
    subject_ref: str
    label: str
    object_ref: str
    category: str
    scopes: tuple[str, ...]
    created_at: str
    summary: str | None = None
    labels: tuple[str, ...] = ()
    confidence: float | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    source: BrainSource = BrainSource()


@dataclass(frozen=True, slots=True)
class BrainAction:
    """A dated event memory recorded: actor -> verb -> object.

    Agent Memory keeps no scope on actions; callers infer it from the facts
    taken from the same turn, as for memory chunks.
    """

    id: str
    actor_ref: str
    verb: str
    # The object entity, or free text when it isn't one.
    object_ref: str | None
    object_text: str | None
    summary: str | None
    category: str
    created_at: str
    occurred_at: str | None = None
    confidence: float | None = None
    source: BrainSource = BrainSource()


@dataclass(frozen=True, slots=True)
class BrainUnknown:
    """Something memory could not settle: an unclear reference, or two
    sources disagreeing about one fact."""

    id: str
    about: str
    reason: str
    resolved: bool
    # Whether memory thinks more input could settle it.
    resolvable: bool
    scopes: tuple[str, ...]
    created_at: str
    entity_ref: str | None = None
    key: str | None = None
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrainInstruction:
    """A standing rule memory follows, e.g. "keep methodology descriptions short".

    Agent Memory only lists these inside GET /state, with no scope and no date:
    they apply everywhere.
    """

    id: str
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class BrainDocument:
    """A file uploaded to memory, to be read and turned into memories.

    Documents carry no scope. `status` is Agent Memory's: queued, processing,
    done or failed (with `error`).
    """

    id: str
    title: str
    file_name: str
    mime_type: str
    size_bytes: int | None
    status: str
    created_at: str
    updated_at: str
    processed_at: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BrainSnapshot:
    entities: list[BrainEntity] = field(default_factory=list)
    facts: list[BrainFact] = field(default_factory=list)
    relations: list[BrainRelation] = field(default_factory=list)
    actions: list[BrainAction] = field(default_factory=list)
    unknowns: list[BrainUnknown] = field(default_factory=list)
    instructions: list[BrainInstruction] = field(default_factory=list)
    documents: list[BrainDocument] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BrainTurn:
    """One captured input or chat message, as Agent Memory keeps it.

    This is the raw text memory chunks and embeds for search (recall hits with
    source "memory_chunk" point back to a session turn). Turns carry no scope.
    """

    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    seq: int = 0


@dataclass(frozen=True, slots=True)
class BrainTurns:
    turns: list[BrainTurn] = field(default_factory=list)
    # Sessions whose turns could not be read this time.
    missing: int = 0


@dataclass(frozen=True, slots=True)
class BrainReplaced:
    facts: list[BrainFact] = field(default_factory=list)
    # Entities whose history could not be read this time.
    missing: int = 0


class MemoryBrain(Protocol):
    async def snapshot(self) -> BrainSnapshot:
        """Every entity, fact and relation in the context.

        Raises MemoryNotConfiguredError or MemoryUnavailableError.
        """
        ...

    async def turns(self, session_ids: Collection[str]) -> BrainTurns:
        """The turns of these sessions. Agent Memory can't list sessions, so
        callers pass the ones facts and relations name as their source.

        A session that fails to load counts in `missing` rather than raising.
        """
        ...

    async def replaced(self, entity_refs: Collection[str]) -> BrainReplaced:
        """The facts newer values replaced, for these entities ("type/key").

        Agent Memory's fact listing leaves them out; they live only in each
        entity's history. An entity that fails to load counts in `missing`.
        """
        ...
