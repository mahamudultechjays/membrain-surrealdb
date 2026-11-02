"""FastAPI dependency wiring — bridges the framework to the composition root.

Concrete adapter selection lives in app/composition.py; this module only
adapts those factories to FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.composition import (
    get_capture_factory,
    get_document_store,
    get_document_store_factory,
    get_memory_capture,
    get_memory_graph,
    get_memory_probe,
    get_preview_cache,
    get_scope_directory,
    get_text_reader,
)
from app.domain.errors import UnknownScopeError
from app.domain.ports.document_store import DocumentStore, DocumentStoreFactory
from app.domain.ports.memory_capture import CaptureFactory, MemoryCapture
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.text_reader import DocumentTextReader
from app.services.capture_flow import PreviewCache
from app.services.scopes import ScopeDirectory

MemoryProbeDep = Annotated[MemoryProbe, Depends(get_memory_probe)]
MemoryCaptureDep = Annotated[MemoryCapture, Depends(get_memory_capture)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
TextReaderDep = Annotated[DocumentTextReader, Depends(get_text_reader)]
MemoryGraphDep = Annotated[MemoryGraph, Depends(get_memory_graph)]
ScopeDirectoryDep = Annotated[ScopeDirectory, Depends(get_scope_directory)]
CaptureFactoryDep = Annotated[CaptureFactory, Depends(get_capture_factory)]
DocumentStoreFactoryDep = Annotated[DocumentStoreFactory, Depends(get_document_store_factory)]
PreviewCacheDep = Annotated[PreviewCache, Depends(get_preview_cache)]


def authorize_scopes(request: Request, directory: ScopeDirectory, scopes: list[str]) -> None:
    """422 for scopes the demo doesn't know; 403 when an X-API-Key caller asks for
    any scope other than its own (the middleware put that on request.state)."""
    try:
        for scope in scopes:
            directory.get(scope)
    except UnknownScopeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown scope: {exc}") from exc
    caller = getattr(request.state, "scope", None)
    if caller is not None and any(scope != caller for scope in scopes):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"This key may only act as {caller}.")
