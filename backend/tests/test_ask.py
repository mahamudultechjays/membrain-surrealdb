import asyncio
from collections.abc import Iterator, Sequence

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqliteFactTags
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
def client(recall: FakeRecall, access: AccessService, tags: SqliteFactTags) -> Iterator[TestClient]:
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


async def _tag(tags: SqliteFactTags, fact_id: str, node: str, goal: str | None, scope: str) -> None:
    await tags.save_auto(
        fact_id, scope, nodes=[node, "sc8"], goals=[goal] if goal else [], version="v1"
    )


def test_results_carry_their_vct_tags(
    client: TestClient, recall: FakeRecall, tags: SqliteFactTags
) -> None:
    asyncio.run(_tag(tags, "f1", "sc6", "ff-mgmt5", PRIYA))
    recall.hits = [_hit("attribute:f1", "UPS rate up"), _hit("attribute:f2", "x")]

    body = _ask(client)

    facts = body["facts"]
    assert facts[0]["tags"]["node"] == {
        "kind": "node",
        "id": "sc6",
        "name": "Select Transport",
        "section_id": facts[0]["tags"]["node"]["section_id"],
        "section": facts[0]["tags"]["node"]["section"],
        "domain_id": "supply-chain",
        "domain": "Supply Chain",
        "source": "auto",
        "rank": 1,
    }
    assert facts[0]["tags"]["goal"]["name"] == "Carrier & Freight Cost Management"
    assert facts[1]["tags"] is None
    assert body["metadata"]["filter"] is None
    assert body["value_facts"] is None


def test_one_recall_feeds_both_the_normal_and_value_driven_lists(
    client: TestClient, recall: FakeRecall, tags: SqliteFactTags
) -> None:
    asyncio.run(_tag(tags, "f1", "sc6", "ff-mgmt5", PRIYA))
    asyncio.run(_tag(tags, "f2", "sc4", "ff-mgmt1", PRIYA))
    asyncio.run(_tag(tags, "f3", "fi4", "ff-mgmt5", ORG))
    recall.hits = [
        _hit("attribute:f1", "UPS"),
        _hit("attribute:f2", "Dallas"),
        _hit("e1", "Acme", "entity"),
        _hit("attribute:f3", "Payout"),
        _hit("attribute:f9", "untagged"),
    ]

    body = _ask(client, goal="ff-mgmt5")

    assert len(recall.calls) == 1
    assert recall.calls[0][1] == 20  # no widening: the filter costs nothing extra
    assert [f["source"]["hit_id"] for f in body["facts"]] == [h.id for h in recall.hits]
    assert [f["source"]["hit_id"] for f in body["value_facts"]] == [
        "attribute:f1",
        "attribute:f3",
    ]
    assert body["metadata"]["filter"] == {
        "goals": ["ff-mgmt5"],
        "nodes": [],
        "domains": [],
        "removed": 3,
    }
    assert body["metadata"]["total_facts"] == 5


def test_kinds_combine_and_domain_matches_through_the_node(
    client: TestClient, recall: FakeRecall, tags: SqliteFactTags
) -> None:
    asyncio.run(_tag(tags, "f1", "sc6", "ff-mgmt5", PRIYA))
    asyncio.run(_tag(tags, "f3", "fi4", "ff-mgmt5", PRIYA))
    asyncio.run(_tag(tags, "f4", "sc4", None, PRIYA))
    recall.hits = [_hit("attribute:f1", "a"), _hit("attribute:f3", "b"), _hit("attribute:f4", "c")]

    def kept(**params: str | list[str]) -> list[str]:
        return [f["source"]["hit_id"] for f in _ask(client, **params)["value_facts"]]

    assert kept(goal="ff-mgmt5", node="fi4") == ["attribute:f3"]
    assert kept(node=["sc6", "sc4"]) == ["attribute:f1", "attribute:f4"]
    assert kept(domain="supply-chain") == ["attribute:f1", "attribute:f4"]
    assert kept(domain="finance,supply-chain", goal="ff-mgmt5") == ["attribute:f1", "attribute:f3"]


def test_a_person_s_tag_wins_in_the_filter(
    client: TestClient, recall: FakeRecall, tags: SqliteFactTags
) -> None:
    asyncio.run(_tag(tags, "f1", "mo1", "ff-mgmt5", PRIYA))
    asyncio.run(tags.set_tag("f1", "node", "fi4", "priya.shah@x.com"))
    recall.hits = [_hit("attribute:f1", "Walmart payout delay")]

    fact = _ask(client, node="fi4")["value_facts"][0]

    assert fact["tags"]["node"]["id"] == "fi4"
    assert fact["tags"]["node"]["source"] == "user"


def test_unknown_filter_ids_are_422(client: TestClient) -> None:
    response = client.get("/api/v1/ask", params={"q": "x", "goal": "zz-1", "node": "sc6,qq"})
    assert response.status_code == 422
    assert "qq, zz-1" in response.json()["detail"]
