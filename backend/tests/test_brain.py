from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_brain, get_scope_registry
from app.domain.errors import MemoryNotConfiguredError
from app.domain.ports.memory_brain import BrainEntity, BrainFact, BrainRelation, BrainSnapshot
from app.main import app
from app.services.access import AccessService
from tests.conftest import FakeRegistry, sign_in

ORG = "org/spreetail"
PRIYA = "org/spreetail/user/priya_shah"
VIDYUL = "org/spreetail/user/vidyul"
VIDYUL_SUB = "org/spreetail/user/vidyul/2u/private"


def _fact(id: str, entity: str, key: str, scope: str, at: str, **extra: str) -> BrainFact:
    return BrainFact(
        id=id,
        entity_ref=entity,
        key=key,
        value=f"{key} value",
        category="context",
        scopes=(scope,),
        created_at=at,
        superseded_by=extra.get("superseded_by"),
    )


SNAPSHOT = BrainSnapshot(
    entities=[
        BrainEntity("organisation/acme", "Acme Logistics", "organisation", "knowledge"),
        BrainEntity("concept/returns", "Returns policy", "concept", "knowledge"),
    ],
    facts=[
        _fact("f1", "organisation/acme", "lead_time", PRIYA, "2026-11-02T10:00:00"),
        _fact("f2", "organisation/acme", "hq", ORG, "2026-11-01T09:00:00"),
        _fact("f3", "concept/returns", "window_days", VIDYUL, "2026-11-03T08:00:00"),
        _fact("f4", "concept/returns", "fee", VIDYUL_SUB, "2026-11-03T09:00:00"),
        _fact(
            "f5",
            "organisation/acme",
            "old_lead_time",
            PRIYA,
            "2026-10-01T00:00:00",
            superseded_by="f1",
        ),
    ],
    relations=[
        BrainRelation(
            "r1",
            "organisation/acme",
            "ships_to",
            "place/reno",
            "context",
            (PRIYA,),
            "2026-11-02T11:00:00",
        ),
    ],
)


class FakeBrain:
    def __init__(self, snapshot: BrainSnapshot | None = SNAPSHOT) -> None:
        self._snapshot = snapshot

    async def snapshot(self) -> BrainSnapshot:
        if self._snapshot is None:
            raise MemoryNotConfiguredError
        return self._snapshot


@pytest.fixture
def client(access: AccessService, registry: FakeRegistry) -> Iterator[TestClient]:
    app.dependency_overrides[get_scope_registry] = lambda: registry
    app.dependency_overrides[get_memory_brain] = lambda: FakeBrain()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _by_name(body: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {e["name"]: e for e in body["entities"]}


def test_a_user_sees_only_the_scopes_they_may_read(client: TestClient) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    body = client.get("/api/v1/brain").json()

    entities = _by_name(body)
    assert list(entities) == ["Acme Logistics"]
    acme = entities["Acme Logistics"]
    assert [f["key"] for f in acme["facts"]] == ["lead_time", "hq", "old_lead_time"]
    assert acme["scopes"] == [ORG, PRIYA]
    assert acme["entity_type"] == "organisation"
    assert acme["updated_at"] == "2026-11-02T11:00:00"
    assert acme["facts"][2]["replaced"] is True
    assert acme["relations"][0]["object_name"] == "reno"
    # Nothing in the fixture has a summary or labels: null and empty, not missing.
    assert (acme["facts"][0]["summary"], acme["facts"][0]["labels"]) == (None, [])
    assert (acme["relations"][0]["summary"], acme["relations"][0]["labels"]) == (None, [])
    replaced = acme["facts"][2]
    assert (replaced["entity_ref"], replaced["superseded_by"]) == ("organisation/acme", "f1")
    assert replaced["source"] == {"kind": None, "ref": None, "session_id": None, "trust": None}
    assert acme["relations"][0]["subject_ref"] == "organisation/acme"
    assert body["scopes"] == [ORG, PRIYA]
    assert (body["total_facts"], body["total_relations"]) == (3, 1)


def test_an_admin_sees_everything_newest_first(client: TestClient) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    body = client.get("/api/v1/brain").json()

    assert [e["name"] for e in body["entities"]] == ["Returns policy", "Acme Logistics"]
    assert body["scopes"] == [ORG, PRIYA, VIDYUL, VIDYUL_SUB]


def test_scope_narrows_exactly_unless_subscopes_are_asked_for(client: TestClient) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    exact = client.get("/api/v1/brain", params={"scope": VIDYUL}).json()
    below = client.get("/api/v1/brain", params={"scope": VIDYUL, "subscopes": "true"}).json()

    assert [f["key"] for f in _by_name(exact)["Returns policy"]["facts"]] == ["window_days"]
    assert [f["key"] for f in _by_name(below)["Returns policy"]["facts"]] == [
        "fee",
        "window_days",
    ]
    assert "Acme Logistics" not in _by_name(exact)


def test_a_scope_the_user_cannot_read_is_refused(client: TestClient) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    response = client.get("/api/v1/brain", params={"scope": f"{ORG},{VIDYUL}"})

    assert response.status_code == 403
    assert VIDYUL in response.json()["detail"]


def test_subscopes_never_widen_past_the_grants(client: TestClient, access: AccessService) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    body = client.get("/api/v1/brain", params={"scope": ORG, "subscopes": "true"}).json()

    keys = {f["key"] for e in body["entities"] for f in e["facts"]}
    # Her own space sits below org/spreetail, so it counts; Vidyul's never does.
    assert keys == {"hq", "lead_time", "old_lead_time"}
    assert VIDYUL not in body["scopes"]


def test_needs_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/brain").status_code == 401


def test_503_when_agent_memory_is_not_configured(client: TestClient) -> None:
    app.dependency_overrides[get_memory_brain] = lambda: FakeBrain(None)
    sign_in(client, "admin@x.com", "Ada Admin")

    assert client.get("/api/v1/brain").status_code == 503
