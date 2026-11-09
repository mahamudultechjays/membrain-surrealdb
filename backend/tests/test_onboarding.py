from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.sqlite import SqliteFactTags, SqliteOnboarding
from app.composition import get_onboarding_service, get_tagger_service
from app.domain.errors import MemoryUnavailableError, UnknownVctNodeError, VctNotSeededError
from app.domain.ports.memory_recall import RecallHit, RecallResult
from app.main import app
from app.services import vct_map
from app.services.access import AccessService
from app.services.onboarding import OnboardingService, node_text, split_clauses
from app.services.tagger import TaggerService
from tests.conftest import FakeRegistry, sign_in

SCOPE = "org/spreetail/vct/nodes"
GOALS = "org/spreetail/vct/goals"
EMAIL = "priya.shah@x.com"
VMAP = vct_map.load()


class FakeRecall:
    """Answers a clause with the nodes whose trigger word it contains, as passages."""

    def __init__(self, routes: dict[str, list[str]]) -> None:
        self.routes = routes
        self.lenses: list[str] = []
        self.error: Exception | None = None

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        self.lenses.append(lens)
        if self.error:
            raise self.error
        ids = next((ids for word, ids in self.routes.items() if word in query), [])
        hits = [
            RecallHit(f"p{n}", node_text(node), "chunk", 0.38)
            for n, i in enumerate(ids)
            if (node := VMAP.node(i))
        ]
        return RecallResult(hits=hits)


class FakePassages:
    def __init__(self) -> None:
        self.written: list[tuple[str, str]] = []

    async def write(self, text: str, scope: str) -> None:
        self.written.append((text, scope))


ROUTES = {
    "warehouse": ["sc4", "sc4", "sc9", "sc8", "sc2"],  # sc4 twice: seeded twice
    "carriers": ["sc6", "mo4"],
    "invoices": ["fi4", "fi3"],
}


@pytest.fixture
def recall() -> FakeRecall:
    return FakeRecall(ROUTES)


@pytest.fixture
def passages() -> FakePassages:
    return FakePassages()


@pytest.fixture
def service(
    recall: FakeRecall, passages: FakePassages, registry: FakeRegistry
) -> OnboardingService:
    return OnboardingService(
        SqliteOnboarding(":memory:"), recall, passages, registry, VMAP, vct_scope=SCOPE
    )


@pytest.fixture
def tagger(recall: FakeRecall, passages: FakePassages, registry: FakeRegistry) -> TaggerService:
    class NoFacts:
        async def page(self, scopes: list[str], *, limit: int, cursor: str | None) -> None:
            raise AssertionError("not listed in onboarding tests")

    return TaggerService(
        SqliteFactTags(":memory:"),
        NoFacts(),  # type: ignore[arg-type]
        recall,
        passages,
        registry,
        VMAP,
        scopes=[],
        nodes_scope=SCOPE,
        goals_scope=GOALS,
    )


@pytest.fixture
def client(
    access: AccessService, service: OnboardingService, tagger: TaggerService
) -> Iterator[TestClient]:
    app.dependency_overrides[get_onboarding_service] = lambda: service
    app.dependency_overrides[get_tagger_service] = lambda: tagger
    with TestClient(app) as test_client:
        sign_in(test_client, EMAIL, "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def test_every_node_has_a_known_domain() -> None:
    domain_ids = {d.id for d in VMAP.domains}

    assert len(VMAP.nodes) == 41
    assert {n.domain_id for n in VMAP.nodes} == domain_ids
    # The map's own domain lists disagree for mkt1; the node's domain_id wins.
    assert [d.id for d in VMAP.domains_of(["mkt1"])] == ["product-innovation"]


def test_split_clauses_on_sentences_commas_and_and() -> None:
    text = "I run receiving at the warehouse and keep counts accurate. Also, I pick carriers daily!"

    assert split_clauses(text) == [
        "I run receiving at the warehouse",
        "keep counts accurate",
        "I pick carriers daily",
    ]
    assert split_clauses("Finance") == ["Finance"]
    assert split_clauses("   ") == []


async def test_suggest_gives_top_three_distinct_nodes_per_clause(
    service: OnboardingService, recall: FakeRecall
) -> None:
    matches = await service.suggest("I manage the warehouse floor. I chase unpaid invoices monthly")

    candidates = [[n.id for n in m.candidates] for m in matches]
    assert candidates == [["sc4", "sc9", "sc8"], ["fi4", "fi3"]]
    assert recall.lenses == [SCOPE, SCOPE]


async def test_suggest_with_nothing_seeded_raises(service: OnboardingService) -> None:
    with pytest.raises(VctNotSeededError):
        await service.suggest("I write poems about the sea")


async def test_confirm_validates_nodes(service: OnboardingService) -> None:
    with pytest.raises(UnknownVctNodeError):
        await service.confirm(EMAIL, primary_work="x", node_ids=["sc4", "nope"])
    with pytest.raises(UnknownVctNodeError):
        await service.confirm(EMAIL, primary_work="x", node_ids=["sc4"], primary_node_id="fi4")
    with pytest.raises(UnknownVctNodeError):
        await service.confirm(EMAIL, primary_work="x", node_ids=[n.id for n in VMAP.nodes[:9]])


async def test_seed_writes_every_node_once(
    service: OnboardingService, passages: FakePassages, registry: FakeRegistry
) -> None:
    first = await service.seed()
    again = await service.seed()
    forced = await service.seed(force=True)

    assert (first, again, forced) == (41, 0, 41)
    assert registry.ensured == [SCOPE, SCOPE]
    assert {scope for _, scope in passages.written} == {SCOPE}
    assert passages.written[0][0].startswith(f"VCT node [{VMAP.nodes[0].id}]")


def test_onboarding_flow_preview_then_confirm(client: TestClient) -> None:
    before = client.get("/api/v1/onboarding").json()
    preview = client.post(
        "/api/v1/onboarding/preview",
        json={"primary_work": "I run the warehouse dock, and I pick carriers for shipments"},
    )
    confirmed = client.post(
        "/api/v1/onboarding/confirm",
        json={
            "primary_work": "I run the warehouse dock, and I pick carriers for shipments",
            "role": "Lead",
            "node_ids": ["sc6", "sc4", "fi4"],
            "primary_node_id": "sc4",
        },
    )
    after = client.get("/api/v1/onboarding").json()

    assert before == {**before, "onboarded": False, "nodes": [], "domains": []}
    assert preview.status_code == 200
    assert preview.json()["suggested"] == ["sc4", "sc6"]
    assert [c["candidates"][0]["id"] for c in preview.json()["clauses"]] == ["sc4", "sc6"]
    assert preview.json()["domains"] == [{"id": "supply-chain", "name": "Supply Chain"}]
    assert confirmed.status_code == 200
    assert after == confirmed.json()
    assert after["onboarded"] is True
    assert after["role"] == "Lead"
    assert [(n["id"], n["rank"], n["is_primary"]) for n in after["nodes"]] == [
        ("sc6", 1, False),
        ("sc4", 2, True),
        ("fi4", 3, False),
    ]
    assert [d["id"] for d in after["domains"]] == ["supply-chain", "finance"]


def test_confirm_again_replaces_the_nodes(client: TestClient) -> None:
    body = {"primary_work": "I chase invoices", "node_ids": ["fi4"]}
    client.post("/api/v1/onboarding/confirm", json={**body, "node_ids": ["sc4", "sc6"]})

    again = client.post("/api/v1/onboarding/confirm", json=body).json()

    assert [n["id"] for n in again["nodes"]] == ["fi4"]
    assert [d["id"] for d in again["domains"]] == ["finance"]


def test_bad_node_is_422_and_memory_down_is_503(client: TestClient, recall: FakeRecall) -> None:
    bad = client.post(
        "/api/v1/onboarding/confirm", json={"primary_work": "abc", "node_ids": ["zz9"]}
    )
    unseeded = client.post("/api/v1/onboarding/preview", json={"primary_work": "I paint walls"})
    recall.error = MemoryUnavailableError("down")
    down = client.post("/api/v1/onboarding/preview", json={"primary_work": "the warehouse"})

    assert bad.status_code == 422
    assert unseeded.status_code == 503
    assert "not seeded" in unseeded.json()["detail"]
    assert down.status_code == 503


def test_vct_map_groups_nodes_by_domain(client: TestClient) -> None:
    body = client.get("/api/v1/vct/map").json()

    assert body["topology_version"] == VMAP.topology_version
    assert len(body["domains"]) == 8
    assert sum(len(d["nodes"]) for d in body["domains"]) == 41


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.get("/api/v1/onboarding").status_code == 401
    assert client.get("/api/v1/vct/map").status_code == 401


def test_admin_seeds_views_and_overrides(client: TestClient, passages: FakePassages) -> None:
    client.post(
        "/api/v1/onboarding/confirm",
        json={"primary_work": "I pick carriers", "team": "Ops", "node_ids": ["sc6"]},
    )
    sign_in(client, "admin@x.com", "Ada Admin")

    seeded = client.post("/api/v1/admin/vct/seed")
    viewed = client.get(f"/api/v1/admin/users/{EMAIL}/onboarding")
    changed = client.put(f"/api/v1/admin/users/{EMAIL}/vct", json={"node_ids": ["fi4", "sc6"]})
    bad = client.put(f"/api/v1/admin/users/{EMAIL}/vct", json={"node_ids": ["zz9"]})
    fresh = client.put("/api/v1/admin/users/new@x.com/vct", json={"node_ids": ["cs2"]})

    assert seeded.json() == {
        "scope": SCOPE,
        "seeded": 41,
        "goals_scope": GOALS,
        "goals_seeded": 42,
        "decoys_seeded": 7,
    }
    assert len(passages.written) == 90
    assert sum(1 for text, _ in passages.written if text.startswith("VCT none")) == 7
    assert [n["id"] for n in viewed.json()["nodes"]] == ["sc6"]
    assert changed.json()["team"] == "Ops"
    assert [(n["id"], n["confirmed_by"]) for n in changed.json()["nodes"]] == [
        ("fi4", "admin"),
        ("sc6", "admin"),
    ]
    assert [d["id"] for d in changed.json()["domains"]] == ["finance", "supply-chain"]
    assert bad.status_code == 422
    assert fresh.json()["domains"] == [{"id": "customer-success", "name": "Customer Success"}]


def test_admin_seed_with_memory_down_is_503(client: TestClient, registry: FakeRegistry) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")
    registry.error = MemoryUnavailableError("down")

    assert client.post("/api/v1/admin/vct/seed").status_code == 503


def test_onboarding_admin_routes_refuse_non_admins(client: TestClient) -> None:
    assert client.post("/api/v1/admin/vct/seed").status_code == 403
    assert client.get(f"/api/v1/admin/users/{EMAIL}/onboarding").status_code == 403
    assert client.put(f"/api/v1/admin/users/{EMAIL}/vct", json={"node_ids": []}).status_code == 403
