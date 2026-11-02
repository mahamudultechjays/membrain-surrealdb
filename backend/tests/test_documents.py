from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.files import PdfAndTextReader
from app.composition import get_document_store, get_memory_capture, get_text_reader
from app.domain.errors import (
    DocumentNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
)
from app.domain.ports.document_store import DocumentDetail, DocumentPassage, DocumentUpload
from app.domain.ports.memory_capture import CaptureResult, ExtractedEntity
from app.main import app
from app.services.access import AccessService
from app.services.document_preview import PREVIEW_CHAR_LIMIT
from tests.conftest import sign_in
from tests.pdf import make_pdf


class FakeCapture:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.error: Exception | None = None

    async def preview(self, text: str) -> CaptureResult:
        self.texts.append(text)
        if self.error:
            raise self.error
        return CaptureResult(
            mode="preview",
            session_id="s1",
            entities=[ExtractedEntity("Returns policy", "policy", "knowledge", is_new=True)],
        )

    async def store(self, text: str) -> CaptureResult:  # pragma: no cover - not used here
        raise AssertionError


class FakeStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []
        self.detail = DocumentDetail(id="d1", status="queued", title="policy.pdf")
        self.error: Exception | None = None

    async def upload(self, filename: str, content: bytes, content_type: str) -> DocumentUpload:
        if self.error:
            raise self.error
        self.uploads.append((filename, content, content_type))
        return DocumentUpload(id="d1", status="queued", deduplicated=False)

    async def get(self, document_id: str) -> DocumentDetail:
        if self.error:
            raise self.error
        return self.detail


@pytest.fixture
def capture() -> FakeCapture:
    return FakeCapture()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(capture: FakeCapture, store: FakeStore, access: AccessService) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_capture] = lambda: capture
    app.dependency_overrides[get_document_store] = lambda: store
    app.dependency_overrides[get_text_reader] = PdfAndTextReader
    with TestClient(app) as test_client:
        sign_in(test_client, "admin@x.com", "Ada Admin")
        yield test_client
    app.dependency_overrides.clear()


PDF = ("policy.pdf", make_pdf("Customers may return items within 30 days."), "application/pdf")


def test_non_admins_are_forbidden(client: TestClient) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    assert client.get("/api/v1/documents/d1").status_code == 403


def test_preview_reads_the_pdf_and_saves_nothing(
    client: TestClient, capture: FakeCapture, store: FakeStore
) -> None:
    response = client.post("/api/v1/documents/preview", files={"file": PDF})

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "policy.pdf"
    assert body["truncated"] is False
    assert body["capture"]["entities"][0]["name"] == "Returns policy"
    assert "return items within 30 days" in capture.texts[0]
    assert store.uploads == []


def test_preview_cuts_long_documents(client: TestClient, capture: FakeCapture) -> None:
    text = "word " * PREVIEW_CHAR_LIMIT

    response = client.post(
        "/api/v1/documents/preview", files={"file": ("long.txt", text.encode(), "text/plain")}
    )

    assert response.json()["truncated"] is True
    assert len(capture.texts[0]) == PREVIEW_CHAR_LIMIT


def test_preview_refuses_a_file_with_no_text(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/preview", files={"file": ("blank.txt", b"   ", "text/plain")}
    )

    assert response.status_code == 422


def test_upload_sends_the_file_once(client: TestClient, store: FakeStore) -> None:
    response = client.post("/api/v1/documents", files={"file": PDF})

    assert response.status_code == 202
    assert response.json() == {"id": "d1", "status": "queued", "deduplicated": False}
    assert [(name, kind) for name, _, kind in store.uploads] == [("policy.pdf", "application/pdf")]


@pytest.mark.parametrize(
    ("file", "code"),
    [
        (("photo.png", b"\x89PNG", "image/png"), 415),
        (("empty.txt", b"", "text/plain"), 422),
    ],
)
def test_upload_refuses_bad_files(
    client: TestClient, store: FakeStore, file: tuple[str, bytes, str], code: int
) -> None:
    response = client.post("/api/v1/documents", files={"file": file})

    assert response.status_code == code
    assert store.uploads == []


def test_upload_refuses_large_files(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.documents.MAX_UPLOAD_BYTES", 10)

    response = client.post(
        "/api/v1/documents", files={"file": ("big.txt", b"x" * 11, "text/plain")}
    )

    assert response.status_code == 413
    assert store.uploads == []


def test_status_reports_progress_then_content(client: TestClient, store: FakeStore) -> None:
    queued = client.get("/api/v1/documents/d1").json()
    assert queued["status"] == "queued"
    assert queued["finished"] is False

    store.detail = DocumentDetail(
        id="d1",
        status="ready",
        title="policy.pdf",
        chunk_count=1,
        keyword_count=2,
        passages=[DocumentPassage(0, "Customers may return items within 30 days.")],
        keywords=["returns", "30 days"],
    )
    ready = client.get("/api/v1/documents/d1").json()

    assert ready["finished"] is True
    assert ready["passages"][0]["text"].startswith("Customers")
    assert ready["keywords"] == ["returns", "30 days"]


def test_status_404_for_unknown_document(client: TestClient, store: FakeStore) -> None:
    store.error = DocumentNotFoundError("nope")

    assert client.get("/api/v1/documents/nope").status_code == 404


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("boom")])
def test_503_when_memory_cannot_answer(
    client: TestClient, capture: FakeCapture, store: FakeStore, error: Exception
) -> None:
    capture.error = error
    store.error = error

    assert client.post("/api/v1/documents/preview", files={"file": PDF}).status_code == 503
    assert client.post("/api/v1/documents", files={"file": PDF}).status_code == 503
    assert client.get("/api/v1/documents/d1").status_code == 503
