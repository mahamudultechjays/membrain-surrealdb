"""Port for reading the plain text out of an uploaded file."""

from typing import Protocol


class DocumentTextReader(Protocol):
    def supports(self, filename: str, content_type: str) -> bool:
        """Whether this file type can be read."""
        ...

    def read(self, filename: str, content: bytes, content_type: str) -> str:
        """The file's text. Raises UnsupportedDocumentError when unreadable."""
        ...
