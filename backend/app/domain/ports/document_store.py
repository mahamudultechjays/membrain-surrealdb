"""Port for uploading documents to memory and following their processing."""

from dataclasses import dataclass, field
from typing import Protocol

# Processing ends in one of these; every other status means "still working".
FINISHED_STATUSES = frozenset({"ready", "failed"})


@dataclass(frozen=True, slots=True)
class DocumentUpload:
    id: str
    status: str
    # True when the same bytes were already uploaded: memory reuses that
    # document instead of storing a second copy.
    deduplicated: bool


@dataclass(frozen=True, slots=True)
class DocumentPassage:
    position: int
    text: str


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    id: str
    status: str
    title: str
    chunk_count: int | None = None
    keyword_count: int | None = None
    error: str | None = None
    # Filled only once the document is ready.
    passages: list[DocumentPassage] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    # ISO-8601 strings as Agent Memory sends them.
    created_at: str | None = None
    updated_at: str | None = None


class DocumentStore(Protocol):
    async def upload(
        self, filename: str, content: bytes, content_type: str, scope: str | None = None
    ) -> DocumentUpload:
        """Send the file once, into `scope` when given; processing continues in the background."""
        ...

    async def get(self, document_id: str) -> DocumentDetail:
        """Current status, plus passages and keywords once ready."""
        ...
