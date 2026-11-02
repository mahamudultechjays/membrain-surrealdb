import asyncio
from collections.abc import Iterator

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
    """Answers per lens; records (lens, k) for every call."""

    def __init__(self) -> None:
        self.by_lens: dict[str, list[RecallHit]] = {}
        self.failing: dict[str, Exception] = {}
        self.calls: list[tuple[str, int]] = []

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        self.calls.append((lens, k))
        if lens in self.failing:
            raise self.failing[lens]
        return RecallResult(
            hits=self.by_lens.get(lens, []), tier="hybrid", query_ms=5, trace_id="tr"
        )


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


def test_reads_each_granted_scope_with_its_own_lens(client: TestClient, recall: FakeRecall) -> None:
    recall.by_lens = {
        ORG: [_hit("c1", "Customers may return items within 30 days.", "chunk")],
        PRIYA: [_hit("a1", "Acme · lead_time_days = 18")],
    }

    body = _ask(client)

    assert [(layer["layer"], layer["area"]) for layer in body["layers"]] == [
        ("org", ORG),
        ("personal", PRIYA),
    ]
    org_fact = body["layers"][0]["facts"][0]
    assert org_fact["source"]["kind"] == "document"
    assert org_fact["source"]["text"] == "Customers may return items within 30 days."
    assert org_fact["source"]["score"] == 0.8
    assert {"trust", "quote", "location"}.isdisjoint(org_fact["source"])
    assert "query_cost_tokens" not in body["metadata"]
    assert body["layers"][1]["owner"] == "Priya Shah"
    assert body["metadata"]["total_facts"] == 2
    assert sorted(recall.calls) == sorted([(ORG, 20), (PRIYA, 10)])


def test_never_reads_another_users_personal_scope(client: TestClient, recall: FakeRecall) -> None:
    recall.by_lens = {ARUN: [_hit("a9", "secret")]}

    body = _ask(client)

    assert body["metadata"]["total_facts"] == 0
    assert all(lens != ARUN for lens, _ in recall.calls)


def test_a_team_grant_adds_the_team_layer(
    client: TestClient, recall: FakeRecall, access: AccessService
) -> None:
    asyncio.run(access.grant("priya.shah@x.com", "Priya Shah", OPS, "read", "team"))

    body = _ask(client)

    assert [layer["area"] for layer in body["layers"]] == [ORG, OPS, PRIYA]


def test_scope_narrows_and_unreadable_scope_is_403(client: TestClient, recall: FakeRecall) -> None:
    body = _ask(client, scope=PRIYA)
    denied = client.get("/api/v1/ask", params={"q": "x", "scope": ARUN})

    assert body["scopes"] == [PRIYA]
    assert recall.calls == [(PRIYA, 10)]
    assert denied.status_code == 403


def test_admin_can_ask_as_two_users_at_once(client: TestClient, recall: FakeRecall) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    body = _ask(client, as_user="priya.shah@x.com,arun.das@x.com")

    assert [layer["area"] for layer in body["layers"]] == [ORG, ARUN, PRIYA]
    assert len(recall.calls) == 3


def test_non_admin_cannot_ask_as_someone_else(client: TestClient) -> None:
    response = client.get("/api/v1/ask", params={"q": "x", "as_user": "arun.das@x.com"})

    assert response.status_code == 403


def test_hit_is_kept_in_the_narrowest_layer(client: TestClient, recall: FakeRecall) -> None:
    shared = _hit("a1", "Acme · lead_time_days = 18")
    recall.by_lens = {ORG: [shared], PRIYA: [shared]}

    body = _ask(client)

    assert body["layers"][0]["facts"] == []
    assert len(body["layers"][1]["facts"]) == 1


def test_one_failing_layer_is_reported_not_fatal(client: TestClient, recall: FakeRecall) -> None:
    recall.failing = {ORG: MemoryUnavailableError("timeout")}

    body = _ask(client)

    assert body["layers"][0]["error"] == "timeout"


@pytest.mark.parametrize(
    "error", [MemoryNotConfiguredError(), MemoryUnavailableError("down"), RuntimeError("boom")]
)
def test_503_when_every_layer_fails(
    client: TestClient, recall: FakeRecall, error: Exception
) -> None:
    recall.failing = {ORG: error, PRIYA: error}

    assert client.get("/api/v1/ask", params={"q": "x"}).status_code == 503


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.get("/api/v1/ask", params={"q": "x"}).status_code == 401
