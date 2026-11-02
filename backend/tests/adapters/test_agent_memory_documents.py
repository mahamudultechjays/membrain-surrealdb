from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError, MemoryNotFoundError
from surrealdb_memory._models.documents import (
    ChunkPage,
    Document,
    DocumentKeywordsResponse,
    UploadResponse,
)

from app.adapters.agent_memory import AgentMemoryDocuments, NotConfiguredDocuments
from app.domain.errors import (
    DocumentNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
)


class FakeKeywords:
    async def for_document(self, doc_id: str) -> DocumentKeywordsResponse:
        return DocumentKeywordsResponse.from_dict(
            {
                "keywords": [
                    {"id": "k1", "text": "refunds", "score": 0.2},
                    {"id": "k2", "text": "returns", "score": 0.9},
                ]
            }
        )


class FakeDocuments:
    def __init__(self, status: str = "ready", error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.keywords = FakeKeywords()
        self.calls: list[Any] = []

    async def upload(self, content: bytes, **kwargs: Any) -> UploadResponse:
        self.calls.append(("upload", content, kwargs))
        if self.error:
            raise self.error
        return UploadResponse.from_dict(
            {"id": "d1", "status": "queued", "contentHash": "h", "deduplicated": True}
        )

    async def get(self, doc_id: str) -> Document:
        if self.error:
            raise self.error
        return Document.from_dict(
            {"id": doc_id, "status": self.status, "title": "policy.pdf", "chunkCount": 1}
        )

    async def chunks(self, doc_id: str, *, page_size: int) -> ChunkPage:
        self.calls.append(("chunks", page_size))
        return ChunkPage.from_dict({"chunks": [{"id": "c1", "position": 0, "text": "Returns..."}]})


class FakeClient:
    def __init__(self, documents: FakeDocuments) -> None:
        self.documents = documents


def adapter(docs: FakeDocuments) -> AgentMemoryDocuments:
    return AgentMemoryDocuments(FakeClient(docs))  # type: ignore[arg-type]


async def test_upload_uses_filename_as_title() -> None:
    docs = FakeDocuments()

    result = await adapter(docs).upload("policy.pdf", b"%PDF", "application/pdf")

    assert (result.id, result.status, result.deduplicated) == ("d1", "queued", True)
    assert docs.calls[0] == (
        "upload",
        b"%PDF",
        {"filename": "policy.pdf", "content_type": "application/pdf", "title": "policy.pdf"},
    )


async def test_ready_document_includes_passages_and_ranked_keywords() -> None:
    detail = await adapter(FakeDocuments()).get("d1")

    assert detail.status == "ready"
    assert detail.passages[0].text == "Returns..."
    assert detail.keywords == ["returns", "refunds"]


async def test_processing_document_skips_content() -> None:
    docs = FakeDocuments(status="embedding")

    detail = await adapter(docs).get("d1")

    assert detail.passages == []
    assert docs.calls == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MemoryNotFoundError(404, "gone"), DocumentNotFoundError),
        (MemoryAuthError(401, "bad key"), MemoryUnavailableError),
    ],
)
async def test_errors_are_translated(error: Exception, expected: type[Exception]) -> None:
    with pytest.raises(expected):
        await adapter(FakeDocuments(error=error)).get("d1")


async def test_upload_failure_is_unavailable() -> None:
    with pytest.raises(MemoryUnavailableError):
        await adapter(FakeDocuments(error=ConnectionError("dns"))).upload(
            "a.txt", b"x", "text/plain"
        )


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredDocuments().upload("a.txt", b"x", "text/plain")
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredDocuments().get("d1")
