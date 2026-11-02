from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError, MemoryNotFoundError

from app.adapters.agent_memory import AgentMemoryGraph, NotConfiguredGraph
from app.domain.errors import EntityNotFoundError, MemoryNotConfiguredError, MemoryUnavailableError

BASE = "/api/v1/ctx"

ENTITY = {
    "entity": {
        "name": "Acme Logistics",
        "entityType": "organisation",
        "memoryCategory": "knowledge",
    },
    "attributes": [
        {
            "key": "lead_time",
            "value": "18 days",
            "memoryCategory": "context",
            "source": {"kind": "turn"},
        }
    ],
    "relations": [
        {"id": "r1", "source": {"kind": "turn", "trust": 0.5}},
        {"id": "r2", "source": {"kind": "elaboration", "trust": 0.3}},
    ],
}

NEIGHBOURHOOD = {
    "neighbours": [
        {
            "label": "ships_to",
            "outbound": True,
            "relationId": "r1",
            "far": {"entity": {"name": "Reno", "entityType": "location"}, "factCount": 2},
        },
        {
            "label": "collaborates_with",
            "outbound": False,
            "relationId": "r2",
            "far": {"entity": {"name": "Kestrel", "entityType": "organisation"}, "factCount": 1},
        },
        {
            "label": "competes_with",
            "outbound": False,
            "relationId": "r3",
            "far": {"entity": {"name": "Kestrel", "entityType": "organisation"}},
        },
    ]
}


class FakeTransport:
    def __init__(self, responses: dict[str, Any], error: Exception | None = None) -> None:
        self.responses = responses
        self.error = error
        self.calls: list[tuple[str, Any]] = []

    async def request(self, method: str, path: str, *, params: Any = None) -> Any:
        self.calls.append((path, params))
        if self.error:
            raise self.error
        return self.responses[path.removeprefix(BASE)]


class FakeClient:
    def __init__(self, transport: FakeTransport) -> None:
        self._transport = transport
        self._base = BASE


def graph(responses: dict[str, Any], error: Exception | None = None) -> AgentMemoryGraph:
    return AgentMemoryGraph(FakeClient(FakeTransport(responses, error)))  # type: ignore[arg-type]


async def test_search_maps_matches() -> None:
    found = await graph(
        {"/entities/search": {"matches": [{"entity": ENTITY["entity"], "factCount": 8}]}}
    ).search("acme", 5)

    assert [(n.id, n.fact_count) for n in found] == [("organisation/Acme Logistics", 8)]


async def test_neighbourhood_builds_directed_edges_with_provenance() -> None:
    path = "/entities/organisation/Acme%20Logistics"

    result = await graph({path: ENTITY, f"{path}/neighbourhood": NEIGHBOURHOOD}).neighbourhood(
        "organisation", "Acme Logistics", 10
    )

    assert result.center.id == "organisation/Acme Logistics"
    assert [n.id for n in result.nodes] == [
        "organisation/Acme Logistics",
        "location/Reno",
        "organisation/Kestrel",
    ]
    ships, collaborates, unknown = result.edges
    assert (ships.source, ships.target, ships.derived) == (
        "organisation/Acme Logistics",
        "location/Reno",
        False,
    )
    assert (collaborates.source, collaborates.derived) == ("organisation/Kestrel", True)
    assert unknown.source_kind is None
    assert result.facts[0].value == "18 days"


async def test_names_are_escaped_in_the_path() -> None:
    adapter = graph({}, error=MemoryNotFoundError(404, "gone"))

    with pytest.raises(EntityNotFoundError):
        await adapter.neighbourhood("project", "Q3/Q4 plan", 10)
    transport: FakeTransport = adapter._client._transport  # type: ignore[assignment]
    assert transport.calls[0][0] == f"{BASE}/entities/project/Q3%2FQ4%20plan"


async def test_other_failures_are_unavailable() -> None:
    with pytest.raises(MemoryUnavailableError):
        await graph({}, error=MemoryAuthError(401, "bad key")).search("a", 1)


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredGraph().search("a", 1)
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredGraph().neighbourhood("person", "A", 1)
