from typing import Any

import pytest

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


async def test_a_failed_listing_is_memory_unavailable() -> None:
    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryBrain(Client(Transport(PAGES, fail=True))).snapshot()  # type: ignore[arg-type]
