"""Port for sending text to memory and seeing what extraction makes of it."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

CaptureMode = Literal["preview", "stored"]


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    name: str
    entity_type: str
    memory_category: str
    is_new: bool | None = None


@dataclass(frozen=True, slots=True)
class ExtractedAttribute:
    key: str
    value: str
    memory_category: str
    # Name of the entity the value belongs to. Preview responses leave the
    # entity id empty, so this is None there.
    entity: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    subject: str
    label: str
    object: str
    memory_category: str


@dataclass(frozen=True, slots=True)
class ExtractedInstruction:
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class ExtractedUncertainty:
    about: str
    reason: str


@dataclass(frozen=True, slots=True)
class CaptureResult:
    mode: CaptureMode
    session_id: str
    turn_id: str | None = None
    entities: list[ExtractedEntity] = field(default_factory=list)
    attributes: list[ExtractedAttribute] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    instructions: list[ExtractedInstruction] = field(default_factory=list)
    uncertainties: list[ExtractedUncertainty] = field(default_factory=list)
    # Stored values this text replaced, as Agent Memory reports them. Their
    # shape is not documented, so they are passed through as plain text.
    corrections: list[str] = field(default_factory=list)


class MemoryCapture(Protocol):
    async def preview(self, text: str) -> CaptureResult:
        """Run extraction without saving anything."""
        ...

    async def store(self, text: str) -> CaptureResult:
        """Run extraction and save the result."""
        ...
