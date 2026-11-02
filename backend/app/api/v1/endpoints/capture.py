"""Capture endpoints: preview what Agent Memory extracts, then store the kept facts.

Every call acts for one demo user scope, using that user's Agent Memory key
when one is configured (see composition.client_for_scope).
"""

import base64
import binascii
import mimetypes
from collections.abc import Awaitable

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import (
    CaptureFactoryDep,
    DocumentStoreDep,
    DocumentStoreFactoryDep,
    PreviewCacheDep,
    ScopeDirectoryDep,
    TextReaderDep,
    authorize_scopes,
)
from app.domain.errors import (
    DocumentNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    UnsupportedDocumentError,
)
from app.domain.ports.document_store import FINISHED_STATUSES, DocumentStore
from app.schemas.capture import (
    CapturePreviewRequest,
    CapturePreviewResponse,
    CaptureStats,
    CaptureStoreRequest,
    CaptureStoreResponse,
    DocumentStatusResponse,
    ExtractedFactOut,
)
from app.services import capture_flow, logger

router = APIRouter(prefix="/capture")

MAX_TEXT_CHARS = 20_000
MAX_FILE_BYTES = 10 * 1024 * 1024
FALLBACK_TYPE = "application/octet-stream"

_ERRORS: dict[int | str, dict[str, str]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory not configured or failing"}
}

STATUS_MESSAGES = {
    "queued": "Waiting in Agent Memory queue...",
    "pending": "Waiting in Agent Memory queue...",
    "processing": "Agent Memory is chunking and indexing the document...",
    "ready": "Processed: passages are searchable.",
}


@router.post("/preview", response_model=CapturePreviewResponse, responses=_ERRORS)
async def preview(
    body: CapturePreviewRequest,
    request: Request,
    directory: ScopeDirectoryDep,
    captures: CaptureFactoryDep,
    documents: DocumentStoreFactoryDep,
    reader: TextReaderDep,
    cache: PreviewCacheDep,
) -> CapturePreviewResponse:
    """What Agent Memory would extract. Text is not saved; a document is uploaded
    once (Agent Memory has no dry run for files) so its processing can be polled."""
    authorize_scopes(request, directory, [body.scope])
    capture = captures(body.scope)

    if body.input_type == "text":
        if len(body.content) > MAX_TEXT_CHARS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Text is limited to {MAX_TEXT_CHARS} characters; use the document tab.",
            )
        found = await _call(
            capture_flow.preview(capture, scope=body.scope, text=body.content, source="text")
        )
    else:
        file_name = body.file_name or "document"
        content_type = mimetypes.guess_type(file_name)[0] or FALLBACK_TYPE
        content = _decode(body.content)
        if not reader.supports(file_name, content_type):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "Only PDF and plain-text files are supported.",
            )
        try:
            text = reader.read(file_name, content, content_type)
        except UnsupportedDocumentError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        shown, truncated = capture_flow.shorten_document(text)
        uploaded = await _call(
            documents(body.scope).upload(file_name, content, content_type, body.scope)
        )
        source = f"document {file_name}" + (" (first words)" if truncated else "")
        found = await _call(
            capture_flow.preview(
                capture,
                scope=body.scope,
                text=shown,
                source=source,
                truncated=truncated,
                doc_id=uploaded.id,
            )
        )

    cache.put(found)
    trace_id = getattr(request.state, "trace_id", None)
    logger.log(
        "[CAPTURE]",
        op="preview",
        trace_id=trace_id,
        scope=body.scope,
        input_type=body.input_type,
        mode=body.config.mode,
        category=body.config.memory_category,
        extracted=len(found.facts),
        truncated=found.truncated,
        doc_id=found.doc_id,
    )
    return CapturePreviewResponse(
        preview_id=found.id,
        scope=found.scope,
        extracted=[
            ExtractedFactOut(
                id=f.id,
                fact=f.fact,
                type=f.type,
                source=f.source,
                note=f.note,
                storable=f.triple is not None,
            )
            for f in found.facts
        ],
        stats=CaptureStats(
            total=len(found.facts),
            high_confidence=found.high_confidence,
            corrections=len(found.corrections),
        ),
        truncated=found.truncated,
        truncated_reason=capture_flow.TRUNCATED_REASON if found.truncated else None,
        doc_id=found.doc_id,
        corrections=found.corrections,
        trace_id=trace_id,
    )


@router.post("/store", response_model=CaptureStoreResponse, responses=_ERRORS)
async def store(
    body: CaptureStoreRequest,
    request: Request,
    directory: ScopeDirectoryDep,
    captures: CaptureFactoryDep,
    cache: PreviewCacheDep,
) -> CaptureStoreResponse:
    """Write the kept facts (or, with infer_full, a fresh full extraction) to memory."""
    authorize_scopes(request, directory, [body.scope])
    found = cache.get(body.preview_id)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Preview not found or expired; run preview again."
        )
    if found.scope != body.scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This preview belongs to another scope.")
    try:
        outcome = await _call(
            capture_flow.store(
                captures(body.scope),
                found,
                kept=body.kept,
                mode=body.config.mode,
                memory_category=body.config.memory_category,
            )
        )
    except capture_flow.CaptureFlowError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    trace_id = getattr(request.state, "trace_id", None)
    logger.log(
        "[CAPTURE]",
        op="store",
        trace_id=trace_id,
        scope=body.scope,
        preview_id=body.preview_id,
        mode=body.config.mode,
        category=body.config.memory_category,
        kept=len(body.kept),
        written=outcome.written,
        corrections=len(outcome.history),
    )
    return CaptureStoreResponse.model_validate(
        {
            "stored_id": outcome.stored_id,
            "written": outcome.written,
            "created_facts": outcome.created_facts,
            "history": outcome.history,
            "trace_id": trace_id,
        }
    )


@router.get("/document/{doc_id}/status", response_model=DocumentStatusResponse, responses=_ERRORS)
async def document_status(
    doc_id: str,
    request: Request,
    directory: ScopeDirectoryDep,
    documents: DocumentStoreFactoryDep,
    shared: DocumentStoreDep,
    scope: str | None = None,
) -> DocumentStatusResponse:
    """Processing status of an uploaded document. Pass the uploader's scope."""
    store: DocumentStore = shared
    if scope is not None:
        authorize_scopes(request, directory, [scope])
        store = documents(scope)
    try:
        detail = await _call(store.get(doc_id))
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.") from exc
    if detail.status == "failed":
        message = f"Processing failed: {detail.error or 'no reason given'}"
    else:
        message = STATUS_MESSAGES.get(detail.status, detail.status)
    return DocumentStatusResponse(
        doc_id=detail.id,
        status=detail.status,
        finished=detail.status in FINISHED_STATUSES,
        chunks=detail.chunk_count or 0,
        keywords=detail.keyword_count or 0,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        message=message,
    )


def _decode(content: str) -> bytes:
    try:
        data = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Document content must be base64."
        ) from exc
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Files are limited to 10 MB.")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty.")
    return data


async def _call[T](call: Awaitable[T]) -> T:
    try:
        return await call
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc
