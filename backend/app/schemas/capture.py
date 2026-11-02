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
    # infer_full: re-run extraction on the source and store all of it.
    # infer_text: store only the kept facts, as given.
    mode: StoreMode = "infer_text"
    # Overrides each kept fact's own category when storing with infer_text.
    memory_category: MemoryCategory | None = None


class CapturePreviewRequest(BaseModel):
    scope: str
    input_type: Literal["text", "document"] = "text"
    config: CaptureConfig = CaptureConfig()
    # Plain text, or the file's bytes base64-encoded when input_type is "document".
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    file_name: str | None = None


class ExtractedFactOut(BaseModel):
    id: str
    fact: str
    type: str
    # Agent Memory reports no per-fact confidence, so this is always null for now.
    confidence: float | None = None
    source: str
    note: str | None
    # False when the fact can only be stored with mode infer_full.
    storable: bool


class CaptureStats(BaseModel):
    total: int
    high_confidence: int
    corrections: int


class CapturePreviewResponse(BaseModel):
    preview_id: str
    scope: str
    extracted: list[ExtractedFactOut]
    stats: CaptureStats
    truncated: bool
    truncated_reason: str | None
    # Agent Memory does not report token cost; null until it does.
    cost_tokens: int | None = None
    # Set for documents: the upload to poll at /capture/document/{doc_id}/status.
    doc_id: str | None = None
    corrections: list[str]
    trace_id: str | None


class CaptureStoreRequest(BaseModel):
    preview_id: str
    scope: str
    kept: list[str] = Field(default_factory=list)
    config: CaptureConfig = CaptureConfig()
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


class DocumentStatusResponse(BaseModel):
    doc_id: str
    status: str
    finished: bool
    chunks: int
    keywords: int
    created_at: str | None
    updated_at: str | None
    message: str
