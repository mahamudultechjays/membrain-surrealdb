from typing import Any

import pytest
from surrealdb_memory import MemoryNotFoundError

from app.adapters.agent_memory.brain import AgentMemoryBrain
from app.domain.errors import MemoryUnavailableError

BASE = "/api/v1/ctx"


class Transport:
    """Serves canned pages; `kind` comes from the last path segment."""

    def __init__(self, pages: dict[str, list[dict[str, Any]]], fail: bool = False) -> None:
        self._pages = pages
        self.fail = fail
        self.calls: list[tuple[str, Any]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.fail:
            raise RuntimeError("boom")
        kind = path.rsplit("/", 1)[1]
        params = kwargs.get("params") or {}
        self.calls.append((kind, params.get("cursor")))
        index = int(params.get("cursor") or 0)
        pages = self._pages[kind]
        more = index + 1 < len(pages)
        return {
            kind: pages[index],
            "page": {"hasMore": more, "nextCursor": str(index + 1) if more else None},
        }


class Entities:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._base = f"{BASE}/entities"


class Client:
    def __init__(self, transport: Transport) -> None:
        self.entities = Entities(transport)


PAGES = {
    "entities": [
        [
            {
                "id": "['concept', 'tier_a_products']",
                "name": "Tier A products",
                "entityType": "concept",
                "memoryCategory": "knowledge",
            },
            {"id": "not a pair", "name": "skipped"},
        ]
    ],
    "attributes": [
        [
            {
                "id": "a1",
                "entity": "entity:concept/tier_a_products",
                "key": "pre_build_weeks",
                "value": "4-5",
                "memoryCategory": "context",
                "summary": "Tier A pre-build takes 4-5 weeks",
                "labels": ["source=email", {"team": "ops"}],
                "confidence": 0.9,
                "importance": "0.5",
                "validFrom": "2026-11-01T00:00:00",
                "source": {"kind": "turn", "ref": "turn:abc", "sessionId": "s1", "trust": 0.5},
                "scope": [["org/spreetail/user/arun/"], ["org/spreetail/user/arun/"]],
                "supersededBy": None,
                "createdAt": "2026-11-03T12:00:00",
            }
        ],
        [
            {
                "id": "a2",
                "entity": "entity:concept/tier_a_products",
                "key": "pre_build_weeks",
                "value": "8-10",
                "scope": [["org/spreetail/user/arun/"]],
                "supersededBy": "a1",
                "createdAt": "2026-11-01T12:00:00",
            }
        ],
    ],
    "relations": [
        [
            {
                "id": "r1",
                "subject": "entity:organisation/spreetail",
                "object": "entity:concept/tier_a_products",
                "label": "manages",
                "scope": [["org/spreetail/"]],
                "createdAt": "2026-11-03T12:01:00",
            }
        ]
    ],
}


async def test_reads_every_page_and_normalises_refs_and_scopes() -> None:
    transport = Transport(PAGES)

    snapshot = await AgentMemoryBrain(Client(transport)).snapshot()  # type: ignore[arg-type]

    assert [(e.ref, e.name, e.entity_type) for e in snapshot.entities] == [
        ("concept/tier_a_products", "Tier A products", "concept")
    ]
    assert [(f.id, f.entity_ref, f.scopes, f.superseded_by) for f in snapshot.facts] == [
        ("a1", "concept/tier_a_products", ("org/spreetail/user/arun",), None),
        ("a2", "concept/tier_a_products", ("org/spreetail/user/arun",), "a1"),
    ]
    assert snapshot.facts[0].summary == "Tier A pre-build takes 4-5 weeks"
    assert snapshot.facts[0].labels == ("source=email", "team=ops")
    assert (snapshot.facts[1].summary, snapshot.facts[1].labels) == (None, ())
    first = snapshot.facts[0]
    assert (first.confidence, first.importance, first.valid_from, first.valid_until) == (
        0.9,
        0.5,
        "2026-11-01T00:00:00",
        None,
    )
    assert (first.source.kind, first.source.ref, first.source.session_id) == (
        "turn",
        "turn:abc",
        "s1",
    )
    assert snapshot.facts[1].source.kind is None
    relation = snapshot.relations[0]
    assert (relation.subject_ref, relation.object_ref, relation.scopes) == (
        "organisation/spreetail",
        "concept/tier_a_products",
        ("org/spreetail",),
    )
    assert ("attributes", "1") in transport.calls


class TurnTransport:
    """Serves session turns two at a time; session "gone" 404s, "bad" fails."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        session = path.split("/sessions/", 1)[1].removesuffix("/turns")
        offset = kwargs["params"]["offset"]
        self.calls.append((session, offset))
        if session == "gone":
            raise MemoryNotFoundError(404, "no such session")
        if session == "bad":
            raise RuntimeError("boom")
        turns = [
            {
                "id": f"turn:{session}-{i}",
                "session": f"session:{session}",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"text {i}",
                "seq": i,
                "createdAt": f"2026-11-0{i + 1}T10:00:00",
            }
            for i in range(3)
        ]
        page = turns[offset : offset + 2]
        return {"turns": page, "page": {"hasMore": offset + 2 < len(turns)}}


async def test_reads_the_turns_of_each_session_once_and_counts_failures() -> None:
    transport = TurnTransport()
    brain = AgentMemoryBrain(Client(transport))  # type: ignore[arg-type]

    found = await brain.turns(["s1", "gone", "bad", "s1", ""])

    assert [(t.id, t.session_id, t.role, t.seq) for t in found.turns] == [
        ("s1-0", "s1", "user", 0),
        ("s1-1", "s1", "assistant", 1),
        ("s1-2", "s1", "user", 2),
    ]
    assert found.missing == 1  # "bad"; a 404 session simply has no turns
    assert sorted(transport.calls) == [("bad", 0), ("gone", 0), ("s1", 0), ("s1", 2)]

    # Read again: s1 and gone come from the cache, bad is tried again.
    transport.calls.clear()
    again = await brain.turns(["s1", "gone", "bad"])
    assert transport.calls == [("bad", 0)]
    assert (len(again.turns), again.missing) == (3, 1)


async def test_a_failed_listing_is_memory_unavailable() -> None:
    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryBrain(Client(Transport(PAGES, fail=True))).snapshot()  # type: ignore[arg-type]


class RouteTransport:
    """Answers by path suffix; anything unrouted fails like an Agent Memory 404."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.paths: list[str] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.paths.append(path)
        for suffix, body in self.routes.items():
            if path.endswith(suffix):
                return body
        raise MemoryNotFoundError(404, "no route")


async def test_reads_actions_and_unknowns_and_survives_their_absence() -> None:
    routes = {
        "/entities": {"entities": [], "page": {}},
        "/attributes": {"attributes": [], "page": {}},
        "/relations": {"relations": [], "page": {}},
        "/actions": {
            "actions": [
                {
                    "id": "a1",
                    "actor": "entity:person/principal:abc",
                    "verb": "reflect",
                    "object": None,
                    "objectText": "Cobalt Ridge grill question",
                    "summary": "Ran it again",
                    "memoryCategory": "context",
                    "confidence": 1.0,
                    "source": {"kind": "turn", "ref": "turn:t1", "sessionId": "s1"},
                    "createdAt": "2026-11-05T08:03:46",
                }
            ],
            "page": {},
        },
        "/uncertainty": {
            "unknowns": [
                {
                    "id": "u1",
                    "about": "It is late again.",
                    "reason": "ambiguous",
                    "resolved": False,
                    "resolvable": True,
                    "entity": "entity:organisation/acme",
                    "key": "lead_time",
                    "scope": [["org/spreetail/user/arun/"]],
                    "createdAt": "2026-11-04T06:49:06",
                }
            ],
            "page": {},
        },
    }
    snapshot = await AgentMemoryBrain(Client(RouteTransport(routes))).snapshot()  # type: ignore[arg-type]

    action = snapshot.actions[0]
    assert (action.actor_ref, action.verb, action.object_ref, action.object_text) == (
        "person/principal:abc",
        "reflect",
        None,
        "Cobalt Ridge grill question",
    )
    assert action.source.ref == "turn:t1"
    unknown = snapshot.unknowns[0]
    assert (unknown.entity_ref, unknown.key, unknown.scopes, unknown.resolvable) == (
        "organisation/acme",
        "lead_time",
        ("org/spreetail/user/arun",),
        True,
    )

    # Without those listings the page still loads, just without them.
    del routes["/actions"], routes["/uncertainty"]
    bare = await AgentMemoryBrain(Client(RouteTransport(routes))).snapshot()  # type: ignore[arg-type]
    assert (bare.actions, bare.unknowns) == ([], [])


async def test_replaced_facts_come_from_entity_history_and_are_cached() -> None:
    history = {
        "history": [
            {"id": "now", "entity": "entity:organisation/acme", "key": "lead_time", "value": "18"},
            {
                "id": "old",
                "entity": "entity:organisation/acme",
                "key": "lead_time",
                "value": "10",
                "supersededBy": "now",
                "scope": [["org/spreetail/"]],
            },
        ]
    }
    transport = RouteTransport({"/entities/organisation/acme/history": history})
    brain = AgentMemoryBrain(Client(transport))  # type: ignore[arg-type]

    found = await brain.replaced(["organisation/acme", "organisation/gone", "not-a-ref"])

    assert [(f.id, f.superseded_by, f.scopes) for f in found.facts] == [
        ("old", "now", ("org/spreetail",))
    ]
    # A missing entity simply has no history; a ref without "/" isn't asked about.
    assert found.missing == 0
    calls = len(transport.paths)
    await brain.replaced(["organisation/acme"])
    assert len(transport.paths) == calls
