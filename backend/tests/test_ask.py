import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_fact_provenance, get_memory_recall
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.fact_provenance import FactProvenance
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


class FakeProvenance:
    """Entity records by (type, name); records every lookup."""

    def __init__(self) -> None:
        self.by_entity: dict[tuple[str, str], dict[str, FactProvenance]] = {}
        self.failing: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, str]] = []

    async def attributes(self, entity_type: str, entity_name: str) -> dict[str, FactProvenance]:
        self.calls.append((entity_type, entity_name))
        if (entity_type, entity_name) in self.failing:
            raise MemoryUnavailableError("entity read failed")
        return self.by_entity.get((entity_type, entity_name), {})


@pytest.fixture
def recall() -> FakeRecall:
    return FakeRecall()


@pytest.fixture
def provenance() -> FakeProvenance:
    return FakeProvenance()


@pytest.fixture
def client(
    recall: FakeRecall, provenance: FakeProvenance, access: AccessService
) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_recall] = lambda: recall
    app.dependency_overrides[get_fact_provenance] = lambda: provenance
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


# --- modes ---------------------------------------------------------------------


def _window_hits(recall: FakeRecall) -> None:
    recall.by_lens = {
        ORG: [_hit("o", "Cobalt Ridge's return window is 30 days", score=0.78)],
        PRIYA: [_hit("p", "Cobalt Ridge's returns window is 60 days", score=0.81)],
    }


def test_without_mode_the_configured_default_answers(
    client: TestClient, recall: FakeRecall
) -> None:
    _window_hits(recall)

    body = _ask(client)

    assert (body["mode"], body["mode_source"]) == ("default", "config")
    assert body["conflicts"] == []
    assert body["metadata"]["tie_margin"] is None
    assert all(f["status"] is None for layer in body["layers"] for f in layer["facts"])


def test_by_layer_flags_conflicts_and_tags_facts(client: TestClient, recall: FakeRecall) -> None:
    _window_hits(recall)

    body = _ask(client, mode="by_layer")

    assert (body["mode"], body["mode_source"]) == ("by_layer", "request")
    [conflict] = body["conflicts"]
    assert conflict["winner_hit_id"] is None
    assert [v["value"] for v in conflict["values"]] == ["60 days", "30 days"]
    assert [v["areas"] for v in conflict["values"]] == [[PRIYA], [ORG]]
    facts = [f for layer in body["layers"] for f in layer["facts"]]
    assert {f["conflict_id"] for f in facts} == {"c1"}
    assert {f["status"] for f in facts} == {None}


def test_best_match_picks_a_winner_and_sets_the_rest_aside(
    client: TestClient, recall: FakeRecall
) -> None:
    _window_hits(recall)

    body = _ask(client, mode="best_match")

    [conflict] = body["conflicts"]
    assert conflict["winner_hit_id"] == "o"
    assert conflict["reason"] == "Scores within 0.10, so the broader Org layer wins"
    assert body["metadata"]["tie_margin"] == 0.1
    org_fact = body["layers"][0]["facts"][0]
    personal_fact = body["layers"][1]["facts"][0]
    assert (org_fact["status"], personal_fact["status"]) == ("used", "set_aside")
    assert personal_fact["reason"] == "Disagrees with the chosen Org value: 30 days"


def test_an_unknown_mode_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/ask", params={"q": "Acme?", "mode": "loudest"})

    assert response.status_code == 422


def test_ask_mode_default_setting_is_used(
    client: TestClient, recall: FakeRecall, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "ASK_MODE_DEFAULT", "best_match")
    _window_hits(recall)

    body = _ask(client)

    assert (body["mode"], body["mode_source"]) == ("best_match", "config")


def test_filler_conflicts_under_the_floor_are_dropped(
    client: TestClient, recall: FakeRecall
) -> None:
    recall.by_lens = {
        ORG: [_hit("o", "Cobalt Ridge's return window is 30 days", score=0.374)],
        PRIYA: [_hit("p", "Cobalt Ridge's returns window is 60 days", score=0.368)],
    }

    body = _ask(client, mode="by_layer")

    assert body["conflicts"] == []


# --- compare -------------------------------------------------------------------


def test_compare_recalls_each_scope_once_for_both_modes(
    client: TestClient, recall: FakeRecall
) -> None:
    _window_hits(recall)

    response = client.get("/api/v1/ask/compare", params={"q": "Cobalt Ridge return window?"})

    assert response.status_code == 200, response.text
    body = response.json()
    # One recall per readable scope, shared by both modes.
    lenses = [lens for lens, _ in recall.calls]
    assert len(lenses) == len(set(lenses))
    best, by_layer = body["best_match"], body["by_layer"]
    assert (best["mode"], by_layer["mode"]) == ("best_match", "by_layer")
    assert best["mode_source"] == by_layer["mode_source"] == "compare"
    assert best["conflicts"][0]["winner_hit_id"] == "o"
    assert by_layer["conflicts"][0]["winner_hit_id"] is None
    # Same hits on both sides; only the verdicts differ.
    assert _hit_ids(best) == _hit_ids(by_layer)
    assert {f["status"] for layer in by_layer["layers"] for f in layer["facts"]} == {None}


def _hit_ids(body: dict) -> list[str]:  # type: ignore[type-arg]
    return [f["source"]["hit_id"] for layer in body["layers"] for f in layer["facts"]]


def test_compare_checks_scopes_like_ask(client: TestClient) -> None:
    response = client.get("/api/v1/ask/compare", params={"q": "x", "scope": ARUN})

    assert response.status_code == 403


def test_compare_is_503_when_every_layer_fails(client: TestClient, recall: FakeRecall) -> None:
    recall.failing = {ORG: MemoryUnavailableError("down"), PRIYA: MemoryUnavailableError("down")}

    assert client.get("/api/v1/ask/compare", params={"q": "x"}).status_code == 503


# --- trust and provenance --------------------------------------------------------


def _lamp(hit_id: str, value: str, score: float) -> RecallHit:
    return RecallHit(
        f"attribute:{hit_id}",
        f"Lumen Desk Lamp's return window is {value}",
        "attribute",
        score,
        entity_type="product",
        entity_name="lumen_desk_lamp",
        key="return_window",
    )


def test_attribute_hits_carry_trust_from_their_entity_record(
    client: TestClient, recall: FakeRecall, provenance: FakeProvenance
) -> None:
    recall.by_lens = {
        ORG: [_lamp("o1", "30 days", 0.5)],
        PRIYA: [_lamp("p1", "60 days", 0.5)],
    }
    provenance.by_entity[("product", "lumen_desk_lamp")] = {
        "o1": FactProvenance(trust=0.95, confidence=0.95, source_kind="upsert"),
        "p1": FactProvenance(trust=0.5, confidence=0.6, source_kind="turn", superseded_by="p2"),
        # Another scope's value of the same key: never recalled, so never shown.
        "x9": FactProvenance(trust=0.95, source_kind="upsert", created_at="secret"),
    }

    body = client.get("/api/v1/ask/compare", params={"q": "Lamp return window?"}).json()

    # One entity, looked up once for both columns.
    assert provenance.calls == [("product", "lumen_desk_lamp")]
    for side in ("best_match", "by_layer"):
        org, personal = (layer["facts"][0]["source"] for layer in body[side]["layers"])
        assert org["provenance"]["trust"] == 0.95
        assert org["provenance"]["source_kind"] == "upsert"
        assert personal["provenance"]["trust"] == 0.5
        assert personal["provenance"]["superseded_by"] == "p2"
    assert "secret" not in str(body)


def test_weak_matches_and_other_kinds_are_not_looked_up(
    client: TestClient, recall: FakeRecall, provenance: FakeProvenance
) -> None:
    recall.by_lens = {
        ORG: [
            _lamp("o1", "30 days", 0.37),
            RecallHit(
                "memory_chunk:m1", "Lamp note", "memory_chunk", 0.6, occurred_at="2026-11-09"
            ),
        ]
    }

    body = _ask(client)

    assert provenance.calls == []
    facts = body["layers"][0]["facts"]
    assert [f["source"]["provenance"] for f in facts] == [None, None]
    assert facts[1]["source"]["occurred_at"] == "2026-11-09"


def test_a_failed_trust_lookup_still_answers(
    client: TestClient, recall: FakeRecall, provenance: FakeProvenance
) -> None:
    recall.by_lens = {ORG: [_lamp("o1", "30 days", 0.5)]}
    provenance.failing.add(("product", "lumen_desk_lamp"))

    body = _ask(client)

    assert body["layers"][0]["facts"][0]["source"]["provenance"] is None
