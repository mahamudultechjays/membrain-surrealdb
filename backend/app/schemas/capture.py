"""Capture schemas: text in, what Agent Memory extracted out."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ports.memory_capture import CaptureMode


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


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
