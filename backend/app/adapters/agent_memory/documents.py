"""DocumentStore adapters for SurrealDB Agent Memory."""

import logging

from surrealdb_memory import AsyncMemory, MemoryNotFoundError

from app.domain.errors import (
    DocumentNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
)
from app.domain.ports.document_store import (
    DocumentDetail,
    DocumentPassage,
    DocumentUpload,
)

logger = logging.getLogger(__name__)

PASSAGES_SHOWN = 5
KEYWORDS_SHOWN = 15


class AgentMemoryDocuments:
    """`POST /documents` once, then `GET /documents/{id}` to follow it.

    Uploads go to the key's default area, with the filename as the title.
    There is no dry run for documents: an upload is stored immediately.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def upload(self, filename: str, content: bytes, content_type: str) -> DocumentUpload:
        try:
            response = await self._client.documents.upload(
                content, filename=filename, content_type=content_type, title=filename
            )
        except Exception as exc:
            logger.warning("Agent Memory document upload failed", exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        return DocumentUpload(
            id=response.id, status=response.status, deduplicated=response.deduplicated
        )

    async def get(self, document_id: str) -> DocumentDetail:
        documents = self._client.documents
        try:
            doc = await documents.get(document_id)
            passages: list[DocumentPassage] = []
            keywords: list[str] = []
            if doc.status == "ready":
                chunks = await documents.chunks(document_id, page_size=PASSAGES_SHOWN)
                passages = [DocumentPassage(c.position, c.text) for c in chunks.chunks]
                found = await documents.keywords.for_document(document_id)
                ranked = sorted(found.keywords, key=lambda k: k.score, reverse=True)
                keywords = [k.text for k in ranked[:KEYWORDS_SHOWN]]
        except MemoryNotFoundError as exc:
            raise DocumentNotFoundError(document_id) from exc
        except Exception as exc:
            logger.warning("Agent Memory document read failed", exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc
        return DocumentDetail(
            id=doc.id,
            status=doc.status,
            title=doc.title,
            chunk_count=doc.chunk_count,
            keyword_count=doc.keyword_count,
            error=doc.error,
            passages=passages,
            keywords=keywords,
        )


class NotConfiguredDocuments:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def upload(self, filename: str, content: bytes, content_type: str) -> DocumentUpload:
        raise MemoryNotConfiguredError

    async def get(self, document_id: str) -> DocumentDetail:
        raise MemoryNotConfiguredError
