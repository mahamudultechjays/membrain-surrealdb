import asyncio
import base64
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.files import PdfAndTextReader
from app.composition import (
    get_document_store,
    get_memory_capture,
    get_preview_cache,
    get_text_reader,
)
from app.domain.errors import (
    DocumentNotFoundError,
    MemoryNotConfiguredError,
    MemoryUnavailableError,
)
from app.domain.ports.document_store import DocumentDetail, DocumentUpload
from app.domain.ports.memory_capture import (
    CaptureResult,
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedRelation,
    ExtractedUncertainty,
    FactTriple,
)
from app.main import app
from app.services.access import AccessService
from app.services.capture_flow import PreviewCache
from tests.conftest import sign_in

# Personal scopes the access service creates for these users on first sign-in.
PRIYA, ARUN = "org/spreetail/user/priya_shah", "org/spreetail/user/arun_das"


class FakeCapture:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple[str, object, str | None]] = []

    async def preview(self, text: str, scope: str | None = None) -> CaptureResult:
        self._record("preview", text, scope)
        return CaptureResult(
            mode="preview",
            session_id="s1",
            entities=[ExtractedEntity("Acme", "organisation", "knowledge", is_new=True)],
            attributes=[ExtractedAttribute("lead_time_days", "18", "knowledge")],
            relations=[ExtractedRelation("Acme", "ships_to", "Reno", "context")],
            uncertainties=[ExtractedUncertainty("Reno", "hedged")],
            corrections=[json.dumps({"key": "lead_time_days", "from": "10"})],
        )

    async def store(self, text: str, scope: str | None = None) -> CaptureResult:
        self._record("store", text, scope)
        return CaptureResult(
            mode="stored",
            session_id="s2",
            attributes=[ExtractedAttribute("lead_time_days", "18", "knowledge", "Acme", "a1")],
        )

    async def store_facts(self, facts: list[FactTriple], scope: str) -> CaptureResult:
        self._record("store_facts", facts, scope)
        return CaptureResult(
            mode="stored",
            session_id="s3",
            corrections=[json.dumps({"key": "lead_time_days", "from": "10"})],
        )

    def _record(self, op: str, payload: object, scope: str | None) -> None:
        self.calls.append((op, payload, scope))
        if self.error:
            raise self.error


class FakeStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str | None]] = []
        self.detail = DocumentDetail(
            id="d1", status="queued", title="p.txt", created_at="2026-11-02T10:00:00Z"
        )
        self.error: Exception | None = None

    async def upload(
        self, filename: str, content: bytes, content_type: str, scope: str | None = None
    ) -> DocumentUpload:
        self.uploads.append((filename, scope))
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
    cache = PreviewCache()
    app.dependency_overrides[get_memory_capture] = lambda: capture
    app.dependency_overrides[get_document_store] = lambda: store
    app.dependency_overrides[get_preview_cache] = lambda: cache
    app.dependency_overrides[get_text_reader] = PdfAndTextReader
    with TestClient(app) as test_client:
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _preview(client: TestClient, **overrides: object) -> dict[str, object]:
    body = {"scope": PRIYA, "input_type": "text", "content": "Acme ships to Reno in 18 days"}
    response = client.post("/api/v1/capture/preview", json={**body, **overrides})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_text_preview_returns_reviewable_facts(client: TestClient, capture: FakeCapture) -> None:
    body = _preview(client)

    assert str(body["preview_id"]).startswith("prev_")
    assert body["extracted"] == [
        {
            "id": "e1",
            "fact": "Acme · lead_time_days = 18",
            "type": "knowledge",
            "source": "text",
            "note": None,
            "storable": True,
            "needs_entity": False,
        },
        {
            "id": "e2",
            "fact": "Acme · ships_to → Reno",
            "type": "context",
            "source": "text",
            "note": "uncertain: hedged",
            "storable": True,
            "needs_entity": False,
        },
    ]
    assert body["entities"] == [{"name": "Acme", "entity_type": "organisation"}]
    assert body["stats"] == {"total": 2, "uncertain": 1, "corrections": 1}
    assert "cost_tokens" not in body
    assert body["truncated"] is False
    assert body["doc_id"] is None
    assert body["scope"] == PRIYA
    assert capture.calls[0] == ("preview", "Acme ships to Reno in 18 days", PRIYA)


def test_scope_defaults_to_the_users_personal_scope(
    client: TestClient, capture: FakeCapture
) -> None:
    response = client.post("/api/v1/capture/preview", json={"content": "Acme ships to Reno"})

    assert response.json()["scope"] == PRIYA
    assert capture.calls[0][2] == PRIYA


@pytest.mark.parametrize("scope", ["org/spreetail", ARUN, "org/user/nobody"])
def test_writing_outside_the_users_write_grants_is_forbidden(
    client: TestClient, capture: FakeCapture, scope: str
) -> None:
    response = client.post("/api/v1/capture/preview", json={"scope": scope, "content": "x"})

    assert response.status_code == 403
    assert capture.calls == []


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.post("/api/v1/capture/preview", json={"content": "x"}).status_code == 401


def test_another_user_cannot_store_from_your_preview(
    client: TestClient, capture: FakeCapture
) -> None:
    preview_id = _preview(client)["preview_id"]
    sign_in(client, "arun.das@x.com", "Arun Das")

    response = client.post("/api/v1/capture/store", json={"preview_id": preview_id, "kept": ["e1"]})

    assert response.status_code == 404
    assert [op for op, _, _ in capture.calls] == ["preview"]


def test_store_is_refused_after_the_grant_is_revoked(
    client: TestClient, access: AccessService
) -> None:
    preview_id = _preview(client)["preview_id"]
    asyncio.run(access.revoke("priya.shah@x.com", PRIYA))

    response = client.post("/api/v1/capture/store", json={"preview_id": preview_id, "kept": ["e1"]})

    assert response.status_code == 403


def test_store_writes_only_kept_facts_as_triples(client: TestClient, capture: FakeCapture) -> None:
    preview_id = _preview(client)["preview_id"]

    response = client.post(
        "/api/v1/capture/store",
        json={
            "preview_id": preview_id,
            "scope": PRIYA,
            "kept": ["e1"],
            "config": {"mode": "triples", "memory_category": "identity"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["written"] == 1
    assert body["created_facts"] == [
        {"entity": "Acme", "key": "lead_time_days", "value": "18", "id": None}
    ]
    assert body["history"][0]["old_value"] == "10"
    assert body["history"][0]["new_value"] == "18"
    assert body["trace_id"].startswith("t-")
    op, facts, scope = capture.calls[-1]
    assert (op, scope) == ("store_facts", PRIYA)
    assert facts == [FactTriple("Acme", "organisation", "lead_time_days", "18", "identity")]


def test_store_full_reextracts_source_text(client: TestClient, capture: FakeCapture) -> None:
    preview_id = _preview(client)["preview_id"]

    response = client.post(
        "/api/v1/capture/store",
        json={"preview_id": preview_id, "scope": PRIYA, "config": {"mode": "full"}},
    )

    assert response.status_code == 200
    assert response.json()["created_facts"][0]["id"] == "a1"
    assert capture.calls[-1] == ("store", "Acme ships to Reno in 18 days", PRIYA)


def test_extract_stores_everything_without_a_preview(
    client: TestClient, capture: FakeCapture
) -> None:
    response = client.post(
        "/api/v1/capture/extract", json={"scope": PRIYA, "content": "Acme ships to Reno"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == PRIYA
    assert body["written"] == 1
    assert body["created_facts"] == [
        {"entity": "Acme", "key": "lead_time_days", "value": "18", "id": "a1"}
    ]
    assert body["doc_id"] is None
    assert body["truncated"] is False
    assert capture.calls == [("store", "Acme ships to Reno", PRIYA)]


def test_extract_checks_the_write_grant(client: TestClient, capture: FakeCapture) -> None:
    response = client.post("/api/v1/capture/extract", json={"scope": ARUN, "content": "x"})

    assert response.status_code == 403
    assert capture.calls == []


def test_extract_document_uploads_it_and_its_status_is_visible(
    client: TestClient, capture: FakeCapture, store: FakeStore
) -> None:
    text = " ".join(f"w{i}" for i in range(2500))
    response = client.post(
        "/api/v1/capture/extract",
        json={
            "scope": PRIYA,
            "input_type": "document",
            "file_name": "policy.txt",
            "content": base64.b64encode(text.encode()).decode(),
        },
    )

    body = response.json()
    assert response.status_code == 200, response.text
    assert body["doc_id"] == "d1"
    assert body["truncated"] is True
    assert store.uploads == [("policy.txt", PRIYA)]
    op, sent, _ = capture.calls[0]
    assert op == "store" and isinstance(sent, str) and len(sent.split()) == 500
    assert client.get("/api/v1/capture/document/d1/status").status_code == 200


def test_store_rejects_unknown_preview_other_scope_and_unknown_ids(client: TestClient) -> None:
    preview_id = _preview(client)["preview_id"]
    url = "/api/v1/capture/store"

    missing = client.post(url, json={"preview_id": "prev_x", "scope": PRIYA, "kept": ["e1"]})
    other = client.post(url, json={"preview_id": preview_id, "scope": ARUN, "kept": ["e1"]})
    bad_ids = client.post(url, json={"preview_id": preview_id, "scope": PRIYA, "kept": ["e9"]})
    none_kept = client.post(url, json={"preview_id": preview_id, "scope": PRIYA, "kept": []})

    assert missing.status_code == 404
    assert other.status_code == 403
    assert bad_ids.status_code == 422
    assert none_kept.status_code == 422


def test_document_preview_uploads_and_truncates_large_files(
    client: TestClient, capture: FakeCapture, store: FakeStore
) -> None:
    text = " ".join(f"w{i}" for i in range(2500))
    body = _preview(
        client,
        input_type="document",
        file_name="policy.txt",
        content=base64.b64encode(text.encode()).decode(),
    )

    assert body["doc_id"] == "d1"
    assert body["truncated"] is True
    assert "500 words" in str(body["truncated_reason"])
    assert store.uploads == [("policy.txt", PRIYA)]
    sent = capture.calls[0][1]
    assert isinstance(sent, str) and len(sent.split()) == 500


@pytest.mark.parametrize(
    ("file_name", "content", "code"),
    [
        ("policy.txt", "not base64!", 422),
        ("image.png", base64.b64encode(b"png").decode(), 415),
    ],
)
def test_document_preview_rejects_bad_input(
    client: TestClient, file_name: str, content: str, code: int
) -> None:
    response = client.post(
        "/api/v1/capture/preview",
        json={"scope": PRIYA, "input_type": "document", "file_name": file_name, "content": content},
    )

    assert response.status_code == code


def test_text_over_limit_is_rejected(client: TestClient) -> None:
    too_long = {"scope": PRIYA, "content": "x" * 20_001}
    response = client.post("/api/v1/capture/preview", json=too_long)

    assert response.status_code == 422


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_503_when_memory_cannot_answer(
    client: TestClient, capture: FakeCapture, error: Exception
) -> None:
    capture.error = error

    response = client.post("/api/v1/capture/preview", json={"scope": PRIYA, "content": "x"})

    assert response.status_code == 503


def _upload(client: TestClient) -> None:
    content = base64.b64encode(b"Customers may return items within 30 days.").decode()
    _preview(client, input_type="document", file_name="policy.txt", content=content)


def test_document_status_for_the_uploader(client: TestClient) -> None:
    _upload(client)

    response = client.get("/api/v1/capture/document/d1/status")

    assert response.status_code == 200
    assert response.json() == {
        "doc_id": "d1",
        "status": "queued",
        "finished": False,
        "chunks": 0,
        "keywords": 0,
        "created_at": "2026-11-02T10:00:00Z",
        "updated_at": None,
        "message": "Waiting in Agent Memory queue...",
    }


def test_document_status_hidden_from_other_users_but_not_admins(client: TestClient) -> None:
    _upload(client)
    sign_in(client, "arun.das@x.com", "Arun Das")
    hidden = client.get("/api/v1/capture/document/d1/status")
    sign_in(client, "admin@x.com", "Ada Admin")
    admin = client.get("/api/v1/capture/document/d1/status")

    assert hidden.status_code == 404
    assert admin.status_code == 200


def test_document_status_failed_and_missing(client: TestClient, store: FakeStore) -> None:
    _upload(client)
    store.detail = DocumentDetail(id="d1", status="failed", title="p", error="bad pdf")
    failed = client.get("/api/v1/capture/document/d1/status").json()
    store.error = DocumentNotFoundError("d1")
    missing = client.get("/api/v1/capture/document/d1/status")

    assert failed["message"] == "Processing failed: bad pdf"
    assert failed["finished"] is True
    assert missing.status_code == 404
