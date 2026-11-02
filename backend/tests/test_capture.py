from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_capture
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_capture import (
    CaptureResult,
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedRelation,
)
from app.main import app


class FakeCapture:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    async def preview(self, text: str) -> CaptureResult:
        return self._result("preview", text)

    async def store(self, text: str) -> CaptureResult:
        return self._result("stored", text)

    def _result(self, mode: str, text: str) -> CaptureResult:
        self.calls.append((mode, text))
        if self.error:
            raise self.error
        return CaptureResult(
            mode=mode,  # type: ignore[arg-type]
            session_id="s1",
            entities=[ExtractedEntity("Acme", "organisation", "context", is_new=True)],
            attributes=[ExtractedAttribute("lead_time", "18 days", "context", entity="Acme")],
            relations=[ExtractedRelation("Acme", "ships_to", "Reno", "context")],
        )


@pytest.fixture
def capture() -> FakeCapture:
    return FakeCapture()


@pytest.fixture
def client(capture: FakeCapture) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_capture] = lambda: capture
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(("path", "mode"), [("/preview", "preview"), ("", "stored")])
def test_returns_extraction(client: TestClient, capture: FakeCapture, path: str, mode: str) -> None:
    response = client.post(f"/api/v1/capture{path}", json={"text": "Acme ships to Reno"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == mode
    assert body["entities"] == [
        {
            "name": "Acme",
            "entity_type": "organisation",
            "memory_category": "context",
            "is_new": True,
        }
    ]
    assert body["attributes"][0]["entity"] == "Acme"
    assert body["relations"][0]["label"] == "ships_to"
    assert capture.calls == [(mode, "Acme ships to Reno")]


def test_rejects_empty_text(client: TestClient, capture: FakeCapture) -> None:
    response = client.post("/api/v1/capture/preview", json={"text": ""})

    assert response.status_code == 422
    assert capture.calls == []


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("boom")])
def test_503_when_memory_cannot_answer(
    client: TestClient, capture: FakeCapture, error: Exception
) -> None:
    capture.error = error

    response = client.post("/api/v1/capture/preview", json={"text": "hi"})

    assert response.status_code == 503
