"""Preview what memory would extract from a document, without saving it.

Agent Memory has no dry run for document uploads, so this reads the file's
text here and runs the text preview on it. It is an approximation: the real
upload splits the document into its own windows before extracting.
"""

from dataclasses import dataclass

from app.domain.ports.memory_capture import CaptureResult, MemoryCapture
from app.domain.ports.text_reader import DocumentTextReader

# Same cap as the text endpoint; longer documents are previewed in part.
PREVIEW_CHAR_LIMIT = 20_000


@dataclass(frozen=True, slots=True)
class DocumentPreview:
    characters: int
    truncated: bool
    result: CaptureResult


async def preview_document(
    reader: DocumentTextReader,
    capture: MemoryCapture,
    *,
    filename: str,
    content: bytes,
    content_type: str,
) -> DocumentPreview:
    text = reader.read(filename, content, content_type)
    truncated = len(text) > PREVIEW_CHAR_LIMIT
    result = await capture.preview(text[:PREVIEW_CHAR_LIMIT])
    return DocumentPreview(characters=len(text), truncated=truncated, result=result)
