"""Document schemas: preview, upload and processing status."""

from pydantic import BaseModel, ConfigDict

from app.schemas.capture import CaptureResponse


class DocumentPreviewResponse(BaseModel):
    filename: str
    characters: int
    # True when only the first part of a long document was previewed.
    truncated: bool
    capture: CaptureResponse


class _FromDomain(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(_FromDomain):
    id: str
    status: str
    deduplicated: bool


class PassageOut(_FromDomain):
    position: int
    text: str


class DocumentDetailResponse(_FromDomain):
    id: str
    status: str
    title: str
    finished: bool
    chunk_count: int | None
    keyword_count: int | None
    error: str | None
    passages: list[PassageOut]
    keywords: list[str]
