"""Brain schemas: entities with their facts and relations, and the memory
chunks they were extracted from, filtered by scope."""

from pydantic import BaseModel

from app.schemas.vct_tags import FactTagsOut


class BrainSourceOut(BaseModel):
    # e.g. "turn" (a captured input) or "elaboration" (inferred from one).
    kind: str | None
    ref: str | None
    session_id: str | None
    trust: float | None


class BrainFactOut(BaseModel):
    id: str
    # The entity's type and key, e.g. "concept/tier_a_products".
    entity_ref: str
    key: str
    value: str
    category: str
    scopes: list[str]
    created_at: str
    # True when a newer value replaced this one.
    replaced: bool
    # Agent Memory's one-sentence version of the fact; null when it has none.
    summary: str | None
    # Descriptive tags such as "source=email"; empty when it has none.
    labels: list[str]
    confidence: float | None
    importance: float | None
    # The fact this one replaced, and the fact that replaced this one.
    supersedes: str | None
    superseded_by: str | None
    valid_from: str | None
    valid_until: str | None
    source: BrainSourceOut
    # The fact's active VCT node and goal; null when it has none.
    vct: FactTagsOut | None = None
    # False until the VCT tagger has handled the fact.
    vct_tagged: bool = False
    # False when the tagger judged the fact not business.
    vct_business: bool = True


class BrainRelationOut(BaseModel):
    id: str
    subject_ref: str
    label: str
    # The related entity's ref and display name.
    object_ref: str
    object_name: str
    category: str
    scopes: list[str]
    created_at: str
    summary: str | None
    labels: list[str]
    confidence: float | None
    valid_from: str | None
    valid_until: str | None
    source: BrainSourceOut


class BrainEntityOut(BaseModel):
    ref: str
    name: str
    entity_type: str
    category: str
    # The scopes this entity's shown facts and relations were written to.
    scopes: list[str]
    updated_at: str
    facts: list[BrainFactOut]
    relations: list[BrainRelationOut]


class BrainChunkOut(BaseModel):
    """A memory chunk: the text of one captured turn, as memory stored it."""

    # The turn's id; facts name it in source.ref as "turn:<id>".
    id: str
    session_id: str
    # "user" for captured input; chat sessions also hold "assistant" turns.
    role: str
    text: str
    created_at: str
    # Inferred from the facts and relations taken from this turn: turns carry no scope.
    scopes: list[str]
    # Ids of the facts and relations extracted from this turn.
    derived: list[str]


class BrainActionOut(BaseModel):
    """A dated event memory recorded: actor -> verb -> object."""

    id: str
    actor_ref: str
    actor_name: str
    verb: str
    object_ref: str | None
    # The object entity's name, or the action's free-text object.
    object_name: str | None
    summary: str | None
    category: str
    created_at: str
    occurred_at: str | None
    confidence: float | None
    # Inferred from the facts taken from the same capture: actions carry no scope.
    scopes: list[str]
    source: BrainSourceOut


class BrainUnknownOut(BaseModel):
    """Something memory could not settle: an unclear reference, or a contradiction."""

    id: str
    about: str
    reason: str
    resolved: bool
    resolvable: bool
    entity_ref: str | None
    entity_name: str | None
    key: str | None
    scopes: list[str]
    labels: list[str]
    created_at: str


class BrainInstructionOut(BaseModel):
    """A standing rule memory follows. No scope: it applies everywhere."""

    id: str
    label: str
    description: str


class BrainDocumentOut(BaseModel):
    """A file uploaded to memory. No scope; listed for admins only."""

    id: str
    title: str
    file_name: str
    mime_type: str
    size_bytes: int | None
    # Agent Memory's: queued, processing, done or failed.
    status: str
    error: str | None
    created_at: str
    updated_at: str
    processed_at: str | None


class BrainResponse(BaseModel):
    entities: list[BrainEntityOut]
    # Every scope the caller may filter by that holds something.
    scopes: list[str]
    total_facts: int
    total_relations: int
    chunks: list[BrainChunkOut]
    total_chunks: int
    # Sessions whose chunks could not be read this time; 0 when all loaded.
    chunks_missing: int
    actions: list[BrainActionOut]
    unknowns: list[BrainUnknownOut]
    instructions: list[BrainInstructionOut] = []
    # Empty for non-admins: documents carry no scope to check a grant against.
    documents: list[BrainDocumentOut] = []
    # True when replaced facts (read from entity histories) are included.
    replaced_loaded: bool
    # Entities whose history could not be read this time; 0 when all loaded.
    replaced_missing: int
