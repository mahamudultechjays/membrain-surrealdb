"""FastAPI dependency wiring — bridges the framework to the composition root.

Concrete adapter selection lives in app/composition.py; this module only
adapts those factories to FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends

from app.composition import (
    get_document_store,
    get_memory_capture,
    get_memory_graph,
    get_memory_probe,
    get_text_reader,
)
from app.domain.ports.document_store import DocumentStore
from app.domain.ports.memory_capture import MemoryCapture
from app.domain.ports.memory_graph import MemoryGraph
from app.domain.ports.memory_probe import MemoryProbe
from app.domain.ports.text_reader import DocumentTextReader

MemoryProbeDep = Annotated[MemoryProbe, Depends(get_memory_probe)]
MemoryCaptureDep = Annotated[MemoryCapture, Depends(get_memory_capture)]
DocumentStoreDep = Annotated[DocumentStore, Depends(get_document_store)]
TextReaderDep = Annotated[DocumentTextReader, Depends(get_text_reader)]
MemoryGraphDep = Annotated[MemoryGraph, Depends(get_memory_graph)]
