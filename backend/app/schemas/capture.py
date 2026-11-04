"""Capture schemas: text in, what Agent Memory extracted out."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ports.memory_capture import CaptureMode
from app.services.capture_flow import StoreMode


class _FromDomain(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EntityOut(_FromDomain):
    name: str
    entity_type: str
    memory_category: str
    is_new: bool | None


class AttributeOut(_FromDomain):
    key: str
    value: str
    memory_category: str
    entity: str | None


class RelationOut(_FromDomain):
    subject: str
    label: str
    object: str
    memory_category: str


class InstructionOut(_FromDomain):
    label: str
    description: str


class UncertaintyOut(_FromDomain):
    about: str
    reason: str


class CaptureResponse(_FromDomain):
    mode: CaptureMode
    session_id: str
    turn_id: str | None
    entities: list[EntityOut]
    attributes: list[AttributeOut]
    relations: list[RelationOut]
    instructions: list[InstructionOut]
    uncertainties: list[UncertaintyOut]
    corrections: list[str]


# --- Capture flow (Nov 2 contract): preview -> review -> store kept facts ---

MemoryCategory = Literal["identity", "knowledge", "context"]

# 10 MB of file bytes, base64-encoded.
MAX_CONTENT_CHARS = 14_000_000


class CaptureConfig(BaseModel):
    # triples: store only the kept facts, as given (infer="triples").
    # full: re-run extraction on the source and store all of it (infer="full").
    mode: StoreMode = "triples"
    # Overrides each kept fact's own category when storing with mode triples.
    memory_category: MemoryCategory | None = None


class CaptureInput(BaseModel):
    # A scope the signed-in user may write; omitted means their personal scope.
    scope: str | None = None
    input_type: Literal["text", "document"] = "text"
    # Plain text, or the file's bytes base64-encoded when input_type is "document".
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    file_name: str | None = None


class CapturePreviewRequest(CaptureInput):
    config: CaptureConfig = CaptureConfig()


class CaptureExtractRequest(CaptureInput):
    """Mode full in one call: extract and store, with no preview to review."""


class ExtractedFactOut(BaseModel):
    id: str
    fact: str
    type: str
    source: str
    note: str | None
    # False when the fact can only be stored with mode full, unless...
    storable: bool
    # ...it needs_entity: the user picks one of the preview's entities for it,
    # and it can then be stored as a triple.
    needs_entity: bool = False


class EntityChoiceOut(BaseModel):
    name: str
    entity_type: str


class CaptureStats(BaseModel):
    total: int
    # Facts Agent Memory raised an uncertainty about (it reports no confidence).
    uncertain: int
    corrections: int


class CapturePreviewResponse(BaseModel):
    preview_id: str
    scope: str
    extracted: list[ExtractedFactOut]
    stats: CaptureStats
    truncated: bool
    truncated_reason: str | None
    # Set for documents: the upload to poll at /capture/document/{doc_id}/status.
    doc_id: str | None = None
    corrections: list[str]
    # Entities the preview found, for facts with needs_entity.
    entities: list[EntityChoiceOut] = Field(default_factory=list)
    trace_id: str | None


class CaptureStoreRequest(BaseModel):
    preview_id: str
    # Optional; when given it must match the preview's scope.
    scope: str | None = None
    kept: list[str] = Field(default_factory=list)
    config: CaptureConfig = CaptureConfig()
    # Fact id -> entity name, for kept facts with needs_entity (mode triples).
    entity_choices: dict[str, str] = Field(default_factory=dict)
    trace_tags: dict[str, str] | None = None


class CreatedFactOut(_FromDomain):
    entity: str
    key: str
    value: str
    id: str | None


class HistoryOut(_FromDomain):
    fact_id: str | None
    key: str | None
    old_value: str | None
    new_value: str | None
    changed_at: str


class CaptureStoreResponse(_FromDomain):
    stored_id: str
    written: int
    created_facts: list[CreatedFactOut]
    history: list[HistoryOut]
    trace_id: str | None


class CaptureExtractResponse(CaptureStoreResponse):
    scope: str
    # Set for documents: the upload to poll at /capture/document/{doc_id}/status.
    doc_id: str | None = None
    # Large documents are extracted from their first words only; the whole file
    # is still uploaded and searchable.
    truncated: bool = False
    truncated_reason: str | None = None


class DocumentStatusResponse(BaseModel):
    doc_id: str
    status: str
    finished: bool
    chunks: int
    keywords: int
    created_at: str | None
    updated_at: str | None
    message: str
