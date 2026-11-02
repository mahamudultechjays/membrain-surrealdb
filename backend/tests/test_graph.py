from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_graph
from app.domain.errors import EntityNotFoundError, MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_graph import EntityFact, EntityGraph, GraphEdge, GraphNode
from app.main import app
from app.services.access import AccessService
from tests.conftest import sign_in

ACME = GraphNode("Acme Logistics", "organisation", "knowledge", 3)
RENO = GraphNode("Reno warehouse", "location", "context", 1)


class FakeGraph:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple[str, ...]] = []

    async def search(self, query: str, limit: int) -> list[GraphNode]:
        self.calls.append(("search", query, str(limit)))
        if self.error:
            raise self.error
        return [ACME]

    async def neighbourhood(self, entity_type: str, name: str, limit: int) -> EntityGraph:
        self.calls.append(("neighbourhood", entity_type, name, str(limit)))
        if self.error:
            raise self.error
        return EntityGraph(
            center=ACME,
            nodes=[ACME, RENO],
            edges=[
                GraphEdge("r1", ACME.id, RENO.id, "ships_to", "turn", 0.5),
                GraphEdge("r2", ACME.id, RENO.id, "located_near", "elaboration", 0.3),
            ],
            facts=[EntityFact("lead_time", "18 days", "context", "turn")],
        )


@pytest.fixture
def graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def client(graph: FakeGraph, access: AccessService) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_graph] = lambda: graph
    with TestClient(app) as test_client:
        sign_in(test_client, "admin@x.com", "Ada Admin")
        yield test_client
    app.dependency_overrides.clear()


def test_non_admins_are_forbidden(client: TestClient) -> None:
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    assert client.get("/api/v1/graph/search?q=acme").status_code == 403


def test_search(client: TestClient, graph: FakeGraph) -> None:
    response = client.get("/api/v1/graph/search", params={"q": "acme"})

    assert response.status_code == 200
    assert response.json()["entities"][0]["id"] == "organisation/Acme Logistics"
    assert graph.calls == [("search", "acme", "20")]


def test_search_needs_a_query(client: TestClient) -> None:
    assert client.get("/api/v1/graph/search", params={"q": ""}).status_code == 422


def test_neighbourhood_marks_derived_edges(client: TestClient, graph: FakeGraph) -> None:
    response = client.get("/api/v1/graph/entities/organisation/Acme Logistics")

    assert response.status_code == 200
    body = response.json()
    assert [n["name"] for n in body["nodes"]] == ["Acme Logistics", "Reno warehouse"]
    assert [e["derived"] for e in body["edges"]] == [False, True]
    assert body["facts"][0]["key"] == "lead_time"
    assert graph.calls == [("neighbourhood", "organisation", "Acme Logistics", "40")]


def test_neighbourhood_accepts_names_with_slashes(client: TestClient, graph: FakeGraph) -> None:
    client.get("/api/v1/graph/entities/project/Q3 / Q4 plan")

    assert graph.calls[0][2] == "Q3 / Q4 plan"


def test_unknown_entity_is_404(client: TestClient, graph: FakeGraph) -> None:
    graph.error = EntityNotFoundError("x")

    assert client.get("/api/v1/graph/entities/person/Nobody").status_code == 404


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("boom")])
def test_503_when_memory_cannot_answer(
    client: TestClient, graph: FakeGraph, error: Exception
) -> None:
    graph.error = error

    assert client.get("/api/v1/graph/search", params={"q": "a"}).status_code == 503
    assert client.get("/api/v1/graph/entities/person/A").status_code == 503
