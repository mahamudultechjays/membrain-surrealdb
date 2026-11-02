from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_recall_factory
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import RecallHit, RecallResult
from app.main import app

PRIYA, ARUN, DEENA = "org/user/u-0001", "org/user/u-0002", "org/user/u-0003"


class FakeRecall:
    """Answers per lens; records (reader scope, lens, k) for every call."""

    def __init__(self) -> None:
        self.by_lens: dict[str, list[RecallHit]] = {}
        self.failing: dict[str, Exception] = {}
        self.calls: list[tuple[str, str, int]] = []

    def for_scope(self, scope: str) -> "ScopedRecall":
        return ScopedRecall(self, scope)


class ScopedRecall:
    def __init__(self, fake: FakeRecall, scope: str) -> None:
        self._fake = fake
        self._scope = scope

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        self._fake.calls.append((self._scope, lens, k))
        if lens in self._fake.failing:
            raise self._fake.failing[lens]
        return RecallResult(
            hits=self._fake.by_lens.get(lens, []), tier="hybrid", query_ms=5, trace_id="tr"
        )


@pytest.fixture
def recall() -> FakeRecall:
    return FakeRecall()


@pytest.fixture
def client(recall: FakeRecall) -> Iterator[TestClient]:
    app.dependency_overrides[get_recall_factory] = lambda: recall.for_scope
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _hit(hit_id: str, text: str, kind: str = "attribute", score: float = 0.8) -> RecallHit:
    return RecallHit(hit_id, text, kind, score)


def test_layers_are_read_in_parallel_with_the_users_key(
    client: TestClient, recall: FakeRecall
) -> None:
    recall.by_lens = {
        "org": [_hit("c1", "Customers may return items within 30 days.", "chunk")],
        PRIYA: [_hit("a1", "Acme · lead_time_days = 18")],
    }

    response = client.get("/api/v1/ask", params={"q": "Acme?", "scope": PRIYA})

    assert response.status_code == 200
    body = response.json()
    assert [(layer["layer"], layer["area"]) for layer in body["layers"]] == [
        ("org", "org"),
        ("team", "org/team/ops"),
        ("personal", PRIYA),
    ]
    org_fact = body["layers"][0]["facts"][0]
    assert org_fact["source"]["kind"] == "document"
    assert org_fact["source"]["quote"] == "Customers may return items within 30 days."
    assert body["layers"][2]["owner"] == "Priya"
    assert body["layers"][2]["facts"][0]["source"]["kind"] == "memory"
    assert body["metadata"]["total_facts"] == 2
    assert body["metadata"]["resolution_tier"] == "hybrid"
    assert sorted(recall.calls) == sorted(
        [(PRIYA, "org", 20), (PRIYA, "org/team/ops", 10), (PRIYA, PRIYA, 10)]
    )


def test_arun_never_reads_priyas_layers(client: TestClient, recall: FakeRecall) -> None:
    recall.by_lens = {PRIYA: [_hit("a1", "secret")]}

    body = client.get("/api/v1/ask", params={"q": "x", "scope": ARUN}).json()

    assert {layer["area"] for layer in body["layers"]} == {"org", "org/team/eng", ARUN}
    assert body["metadata"]["total_facts"] == 0
    assert all(lens != PRIYA for _, lens, _ in recall.calls)


def test_combined_scopes_read_each_layer_once(client: TestClient, recall: FakeRecall) -> None:
    body = client.get("/api/v1/ask", params={"q": "x", "scope": f"{PRIYA},{DEENA}"}).json()

    assert body["scopes"] == [PRIYA, DEENA]
    assert [layer["area"] for layer in body["layers"]] == ["org", "org/team/ops", PRIYA, DEENA]
    assert len(recall.calls) == 4


def test_hit_is_kept_in_the_narrowest_layer(client: TestClient, recall: FakeRecall) -> None:
    shared = _hit("a1", "Acme · lead_time_days = 18")
    recall.by_lens = {"org": [shared], PRIYA: [shared]}

    body = client.get("/api/v1/ask", params={"q": "x", "scope": PRIYA}).json()

    assert body["layers"][0]["facts"] == []
    assert len(body["layers"][2]["facts"]) == 1


def test_one_failing_layer_is_reported_not_fatal(client: TestClient, recall: FakeRecall) -> None:
    recall.failing = {"org/team/ops": MemoryUnavailableError("403 not granted")}

    response = client.get("/api/v1/ask", params={"q": "x", "scope": PRIYA})

    assert response.status_code == 200
    assert response.json()["layers"][1]["error"] == "403 not granted"


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_503_when_every_layer_fails(
    client: TestClient, recall: FakeRecall, error: Exception
) -> None:
    recall.failing = dict.fromkeys(("org", "org/team/ops", PRIYA), error)

    response = client.get("/api/v1/ask", params={"q": "x", "scope": PRIYA})

    assert response.status_code == 503


def test_unexpected_errors_become_503(client: TestClient, recall: FakeRecall) -> None:
    recall.failing = {lens: RuntimeError("boom") for lens in ("org", "org/team/ops", PRIYA)}

    assert client.get("/api/v1/ask", params={"q": "x", "scope": PRIYA}).status_code == 503


def test_scope_is_required_and_validated(client: TestClient) -> None:
    assert client.get("/api/v1/ask", params={"q": "x"}).status_code == 422
    assert client.get("/api/v1/ask", params={"q": "x", "scope": "nope"}).status_code == 422
