"""Document endpoints: preview locally, upload once, then poll the status."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.deps import DocumentStoreDep, MemoryCaptureDep, TextReaderDep
from app.domain.errors import (
    DocumentNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    UnsupportedDocumentError,
)
from app.domain.ports.document_store import FINISHED_STATUSES
from app.domain.ports.text_reader import DocumentTextReader
from app.schemas.capture import CaptureResponse
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentPreviewResponse,
    DocumentUploadResponse,
)
from app.services.document_preview import preview_document

router = APIRouter(prefix="/documents")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
FALLBACK_TYPE = "application/octet-stream"


@router.post("/preview", response_model=DocumentPreviewResponse)
async def preview(
    file: UploadFile, reader: TextReaderDep, capture: MemoryCaptureDep
) -> DocumentPreviewResponse:
    """What memory would extract from the file's text. Nothing is saved."""
    filename, content, content_type = await _read(file, reader)
    try:
        found = await preview_document(
            reader, capture, filename=filename, content=content, content_type=content_type
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    return DocumentPreviewResponse(
        filename=filename,
        characters=found.characters,
        truncated=found.truncated,
        capture=CaptureResponse.model_validate(found.result),
    )


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload(
    file: UploadFile, reader: TextReaderDep, store: DocumentStoreDep
) -> DocumentUploadResponse:
    """Upload the file once. Processing continues in Agent Memory; poll its status."""
    filename, content, content_type = await _read(file, reader)
    try:
        uploaded = await store.upload(filename, content, content_type)
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    return DocumentUploadResponse.model_validate(uploaded)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(document_id: str, store: DocumentStoreDep) -> DocumentDetailResponse:
    """Processing status, with passages and keywords once ready."""
    try:
        detail = await store.get(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc
    except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
        raise _unavailable(exc) from exc
    return DocumentDetailResponse.model_validate(
        {**asdict(detail), "finished": detail.status in FINISHED_STATUSES}
    )


async def _read(file: UploadFile, reader: DocumentTextReader) -> tuple[str, bytes, str]:
    filename = file.filename or "document"
    content_type = file.content_type or FALLBACK_TYPE
    if not reader.supports(filename, content_type):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF and plain-text files are supported."
        )
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Files are limited to 10 MB.")
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty.")
    return filename, content, content_type


def _unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryNotConfiguredError):
        detail = "Agent Memory is not configured. Set AGENT_MEMORY_* in .env."
    else:
        detail = f"Agent Memory call failed: {exc}"
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)
