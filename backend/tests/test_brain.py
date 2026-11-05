from collections.abc import Collection, Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_brain, get_scope_registry
from app.domain.errors import MemoryNotConfiguredError
from app.domain.ports.memory_brain import (
    BrainAction,
    BrainEntity,
    BrainFact,
    BrainRelation,
    BrainReplaced,
    BrainSnapshot,
    BrainSource,
    BrainTurn,
    BrainTurns,
    BrainUnknown,
)
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
        source=BrainSource(
            kind="turn" if "turn" in extra else None,
            ref=f"turn:{extra['turn']}" if "turn" in extra else None,
            session_id=extra.get("session"),
        ),
    )


SNAPSHOT = BrainSnapshot(
    entities=[
        BrainEntity("organisation/acme", "Acme Logistics", "organisation", "knowledge"),
        BrainEntity("concept/returns", "Returns policy", "concept", "knowledge"),
    ],
    facts=[
        _fact(
            "f1",
            "organisation/acme",
            "lead_time",
            PRIYA,
            "2026-11-02T10:00:00",
            turn="t1",
            session="s1",
        ),
        _fact("f2", "organisation/acme", "hq", ORG, "2026-11-01T09:00:00"),
        _fact(
            "f3",
            "concept/returns",
            "window_days",
            VIDYUL,
            "2026-11-03T08:00:00",
            turn="t3",
            session="s3",
        ),
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
    actions=[
        # Captured with f1, so in Priya's space.
        BrainAction(
            "a1",
            "person/principal:abc",
            "shipped",
            "organisation/acme",
            None,
            "self shipped with Acme",
            "context",
            "2026-11-02T10:05:00",
            source=BrainSource(kind="turn", ref="turn:t1", session_id="s1"),
        ),
        # Same session as f3 (no turn match): Vidyul's space.
        BrainAction(
            "a2",
            "organisation/acme",
            "delayed",
            None,
            "Reno shipment",
            None,
            "context",
            "2026-11-03T08:30:00",
            source=BrainSource(kind="turn", ref="turn:other", session_id="s3"),
        ),
    ],
    unknowns=[
        BrainUnknown(
            "u1",
            "It is late again.",
            "'It' is ambiguous",
            resolved=False,
            resolvable=False,
            scopes=(PRIYA,),
            created_at="2026-11-02T10:06:00",
            entity_ref="organisation/acme",
            key="lead_time",
        ),
        BrainUnknown(
            "u2", "Fee", "Two sources disagree", True, True, (VIDYUL,), "2026-11-03T09:00:00"
        ),
    ],
)

# What Acme's history holds beyond the listing: a value f1 replaced.
OLD_FACT = BrainFact(
    id="f0",
    entity_ref="organisation/acme",
    key="lead_time",
    value="10 days",
    category="knowledge",
    scopes=(PRIYA,),
    created_at="2026-09-01T00:00:00",
    superseded_by="f1",
)


TURNS = {
    # Priya's capture, and a chat reply in the same session that produced nothing.
    "s1": [
        BrainTurn("t1", "s1", "user", "Acme's lead time is 6 days.", "2026-11-02T09:59:00"),
        BrainTurn("t2", "s1", "assistant", "Noted.", "2026-11-02T09:59:30", seq=1),
    ],
    "s3": [BrainTurn("t3", "s3", "user", "Returns window is 30 days.", "2026-11-03T07:59:00")],
}


class FakeBrain:
    def __init__(self, snapshot: BrainSnapshot | None = SNAPSHOT, missing: int = 0) -> None:
        self._snapshot = snapshot
        self._missing = missing
        self.asked: list[str] = []
        self.histories: list[str] = []

    async def snapshot(self) -> BrainSnapshot:
        if self._snapshot is None:
            raise MemoryNotConfiguredError
        return self._snapshot

    async def turns(self, session_ids: Collection[str]) -> BrainTurns:
        self.asked = list(session_ids)
        found = [t for s in session_ids for t in TURNS.get(s, [])]
        return BrainTurns(turns=found, missing=self._missing)

    async def replaced(self, entity_refs: Collection[str]) -> BrainReplaced:
        self.histories = list(entity_refs)
        found = [OLD_FACT] if "organisation/acme" in self.histories else []
        return BrainReplaced(facts=found, missing=0)


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


def test_memory_chunks_are_the_turns_facts_came_from_in_readable_scopes(
    access: AccessService, registry: FakeRegistry
) -> None:
    fake = FakeBrain(missing=1)
    app.dependency_overrides[get_scope_registry] = lambda: registry
    app.dependency_overrides[get_memory_brain] = lambda: fake
    try:
        with TestClient(app) as client:
            sign_in(client, "priya.shah@x.com", "Priya Shah")
            body = client.get("/api/v1/brain").json()
            skipped = client.get("/api/v1/brain", params={"chunks": "false"}).json()
    finally:
        app.dependency_overrides.clear()

    # Only sessions behind facts she may read are fetched: never Vidyul's s3.
    assert fake.asked == ["s1"]
    assert [(c["id"], c["role"]) for c in body["chunks"]] == [
        ("t2", "assistant"),
        ("t1", "user"),
    ]
    by_id = {c["id"]: c for c in body["chunks"]}
    # The turn's own facts give it its scope; the reply borrows its session's.
    assert (by_id["t1"]["derived"], by_id["t1"]["scopes"]) == (["f1"], [PRIYA])
    assert (by_id["t2"]["derived"], by_id["t2"]["scopes"]) == ([], [PRIYA])
    assert by_id["t1"]["text"] == "Acme's lead time is 6 days."
    assert (body["total_chunks"], body["chunks_missing"]) == (2, 1)
    assert (skipped["chunks"], skipped["chunks_missing"]) == ([], 0)


def test_chunks_follow_the_scope_narrowing(client: TestClient) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    body = client.get("/api/v1/brain", params={"scope": VIDYUL}).json()

    assert [c["id"] for c in body["chunks"]] == ["t3"]
    assert body["chunks"][0]["scopes"] == [VIDYUL]


def test_needs_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/brain").status_code == 401


def test_503_when_agent_memory_is_not_configured(client: TestClient) -> None:
    app.dependency_overrides[get_memory_brain] = lambda: FakeBrain(None)
    sign_in(client, "admin@x.com", "Ada Admin")

    assert client.get("/api/v1/brain").status_code == 503


def test_actions_take_the_space_of_their_capture_and_unknowns_their_own(
    client: TestClient,
) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    body = client.get("/api/v1/brain").json()

    assert [a["id"] for a in body["actions"]] == ["a1"]
    a1 = body["actions"][0]
    assert (a1["actor_name"], a1["verb"], a1["object_name"]) == (
        "self",
        "shipped",
        "Acme Logistics",
    )
    assert a1["scopes"] == [PRIYA]
    assert [u["id"] for u in body["unknowns"]] == ["u1"]
    u1 = body["unknowns"][0]
    assert (u1["entity_name"], u1["key"], u1["resolved"]) == ("Acme Logistics", "lead_time", False)


def test_an_action_with_free_text_object_keeps_it(client: TestClient) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    body = client.get("/api/v1/brain", params={"scope": VIDYUL}).json()

    assert [(a["id"], a["object_name"], a["scopes"]) for a in body["actions"]] == [
        ("a2", "Reno shipment", [VIDYUL])
    ]


def test_replaced_values_come_from_entity_histories_only_when_asked(
    access: AccessService, registry: FakeRegistry
) -> None:
    fake = FakeBrain()
    app.dependency_overrides[get_scope_registry] = lambda: registry
    app.dependency_overrides[get_memory_brain] = lambda: fake
    try:
        with TestClient(app) as client:
            sign_in(client, "priya.shah@x.com", "Priya Shah")
            plain = client.get("/api/v1/brain").json()
            assert fake.histories == []
            full = client.get("/api/v1/brain", params={"replaced": "true"}).json()
    finally:
        app.dependency_overrides.clear()

    def acme_keys(body: dict) -> list[tuple[str, bool]]:  # type: ignore[type-arg]
        acme = next(e for e in body["entities"] if e["name"] == "Acme Logistics")
        return [(f["id"], f["replaced"]) for f in acme["facts"]]

    assert ("f0", True) not in acme_keys(plain)
    assert plain["replaced_loaded"] is False
    # Only entities with a fact Priya may read have their history read.
    assert fake.histories == ["organisation/acme"]
    assert ("f0", True) in acme_keys(full)
    assert (full["replaced_loaded"], full["replaced_missing"]) == (True, 0)
