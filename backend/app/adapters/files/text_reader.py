"""DocumentTextReader for PDFs and plain-text files."""

import io
import logging
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.domain.errors import UnsupportedDocumentError

logger = logging.getLogger(__name__)

PDF_TYPES = {"application/pdf"}
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv"}
PDF_SUFFIXES = {".pdf"}


class PdfAndTextReader:
    """Reads text from PDFs (pypdf) and UTF-8 text files.

    Scanned PDFs have no text layer, so they come back empty and are refused.
    """

    def supports(self, filename: str, content_type: str) -> bool:
        return self._is_pdf(filename, content_type) or self._is_text(filename, content_type)

    def read(self, filename: str, content: bytes, content_type: str) -> str:
        if self._is_pdf(filename, content_type):
            text = self._read_pdf(content)
        elif self._is_text(filename, content_type):
            text = content.decode("utf-8", errors="replace")
        else:
            raise UnsupportedDocumentError("Only PDF and plain-text files are supported.")
        text = text.strip()
        if not text:
            raise UnsupportedDocumentError("The file has no readable text.")
        return text

    @staticmethod
    def _suffix(filename: str) -> str:
        return PurePath(filename).suffix.lower()

    def _is_pdf(self, filename: str, content_type: str) -> bool:
        return content_type in PDF_TYPES or self._suffix(filename) in PDF_SUFFIXES

    def _is_text(self, filename: str, content_type: str) -> bool:
        return content_type.startswith("text/") or self._suffix(filename) in TEXT_SUFFIXES

    @staticmethod
    def _read_pdf(content: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(content))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except (PyPdfError, ValueError, OSError) as exc:
            logger.info("Could not read PDF", exc_info=True)
            raise UnsupportedDocumentError("The PDF could not be read.") from exc
