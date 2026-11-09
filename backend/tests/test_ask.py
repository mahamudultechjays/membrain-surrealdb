import asyncio
from collections.abc import Iterator, Sequence

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_recall
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_recall import RecallHit, RecallResult
from app.main import app
from app.services.access import AccessService
from tests.conftest import sign_in

ORG, OPS = "org/spreetail", "org/spreetail/team/ops"
PRIYA, ARUN = "org/spreetail/user/priya_shah", "org/spreetail/user/arun_das"


class FakeRecall:
    """One ranked list per call, as Agent Memory returns it; records (lenses, k)."""

    def __init__(self) -> None:
        self.hits: list[RecallHit] = []
        self.error: Exception | None = None
        self.calls: list[tuple[tuple[str, ...], int]] = []

    async def recall(self, query: str, *, lenses: Sequence[str], k: int) -> RecallResult:
        self.calls.append((tuple(lenses), k))
        if self.error:
            raise self.error
        return RecallResult(hits=self.hits, tier="hybrid", query_ms=5, trace_id="tr")


@pytest.fixture
def recall() -> FakeRecall:
    return FakeRecall()


@pytest.fixture
def client(recall: FakeRecall, access: AccessService) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_recall] = lambda: recall
    with TestClient(app) as test_client:
        # Both users exist; the session ends up as Priya.
        sign_in(test_client, "arun.das@x.com", "Arun Das")
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _hit(hit_id: str, text: str, kind: str = "attribute", score: float = 0.8) -> RecallHit:
    return RecallHit(hit_id, text, kind, score)


def _ask(client: TestClient, **params: str | list[str]) -> dict:  # type: ignore[type-arg]
    response = client.get("/api/v1/ask", params={"q": "Acme?", **params})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_one_recall_across_every_granted_scope(client: TestClient, recall: FakeRecall) -> None:
    recall.hits = [
        _hit("a1", "Acme · lead_time_days = 18", score=0.9),
        _hit("c1", "Customers may return items within 30 days.", "chunk", score=0.6),
    ]

    body = _ask(client)

    assert recall.calls == [((ORG, PRIYA), 20)]
    assert body["scopes"] == [ORG, PRIYA]
    # Agent Memory's own ranking, unchanged and not grouped by layer.
    assert [f["source"]["hit_id"] for f in body["facts"]] == ["a1", "c1"]
    doc = body["facts"][1]["source"]
    assert doc["kind"] == "document"
    assert doc["text"] == "Customers may return items within 30 days."
    assert doc["score"] == 0.6
    assert {"trust", "quote", "location"}.isdisjoint(doc)
    assert "layers" not in body
    assert body["metadata"]["total_facts"] == 2
    assert body["metadata"]["resolution_tier"] == "hybrid"
    assert body["metadata"]["trace_ids"] == ["tr"]


def test_never_reads_another_users_personal_scope(client: TestClient, recall: FakeRecall) -> None:
    _ask(client)

    [(lenses, _)] = recall.calls
    assert ARUN not in lenses


def test_a_team_grant_adds_the_team_scope(
    client: TestClient, recall: FakeRecall, access: AccessService
) -> None:
    asyncio.run(access.grant("priya.shah@x.com", "Priya Shah", OPS, "read", "team"))

    body = _ask(client)

    assert recall.calls == [((ORG, OPS, PRIYA), 20)]
    assert body["scopes"] == [ORG, OPS, PRIYA]


def test_scope_narrows_and_unreadable_scope_is_403(client: TestClient, recall: FakeRecall) -> None:
    body = _ask(client, scope=PRIYA)
    denied = client.get("/api/v1/ask", params={"q": "x", "scope": ARUN})

    assert body["scopes"] == [PRIYA]
    assert recall.calls == [((PRIYA,), 20)]
    assert denied.status_code == 403


def test_admin_can_ask_as_two_users_at_once(client: TestClient, recall: FakeRecall) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    body = _ask(client, as_user="priya.shah@x.com,arun.das@x.com")

    assert body["scopes"] == [ORG, ARUN, PRIYA]
    assert recall.calls == [((ORG, ARUN, PRIYA), 20)]


def test_non_admin_cannot_ask_as_someone_else(client: TestClient) -> None:
    response = client.get("/api/v1/ask", params={"q": "x", "as_user": "arun.das@x.com"})

    assert response.status_code == 403


# The adapter turns any client failure into MemoryUnavailableError.
@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_503_when_recall_fails(client: TestClient, recall: FakeRecall, error: Exception) -> None:
    recall.error = error

    assert client.get("/api/v1/ask", params={"q": "x"}).status_code == 503


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.get("/api/v1/ask", params={"q": "x"}).status_code == 401
