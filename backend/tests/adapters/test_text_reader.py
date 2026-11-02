import pytest

from app.adapters.files import PdfAndTextReader
from app.domain.errors import UnsupportedDocumentError
from tests.pdf import make_pdf

reader = PdfAndTextReader()


def test_reads_pdf_text() -> None:
    pdf = make_pdf("Returns within 30 days.", "Refunds in 5 business days.")

    text = reader.read("policy.pdf", pdf, "application/pdf")

    assert "Returns within 30 days." in text
    assert "Refunds in 5 business days." in text


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("notes.md", "application/octet-stream"), ("notes", "text/plain")],
)
def test_reads_text_files(filename: str, content_type: str) -> None:
    assert reader.read(filename, b"  Acme ships late.\n", content_type) == "Acme ships late."


@pytest.mark.parametrize(
    ("filename", "content_type", "expected"),
    [
        ("a.pdf", "application/octet-stream", True),
        ("a", "application/pdf", True),
        ("a.csv", "", True),
        ("a.png", "image/png", False),
        ("a.docx", "application/vnd.openxmlformats-officedocument", False),
    ],
)
def test_supports(filename: str, content_type: str, expected: bool) -> None:
    assert reader.supports(filename, content_type) is expected


def test_refuses_unsupported_types() -> None:
    with pytest.raises(UnsupportedDocumentError):
        reader.read("photo.png", b"\x89PNG", "image/png")


def test_refuses_broken_pdf() -> None:
    with pytest.raises(UnsupportedDocumentError):
        reader.read("broken.pdf", b"not a pdf", "application/pdf")


def test_refuses_pdf_without_text() -> None:
    with pytest.raises(UnsupportedDocumentError):
        reader.read("scan.pdf", make_pdf(), "application/pdf")
