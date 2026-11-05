from typing import Any

import pytest

from app.adapters.agent_memory import AgentMemoryPeople, NotConfiguredPeople
from app.adapters.agent_memory.people import name_from
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_people import MemoryPerson

PAGES = [
    {
        "principals": [
            {
                "id": "a",
                "kind": "human",
                "displayName": "Arun.Das@x.com",
                "grants": {"memory:read": ["/*"], "bad": "x"},
            },
            {"id": "b", "kind": "service", "displayName": "system", "grants": {}},
        ],
        "page": {"nextCursor": "c1", "hasMore": True},
    },
    {
        "principals": [
            {"id": "c", "kind": "human", "displayName": "admin", "grants": {}},
            {"id": "d", "kind": "human", "displayName": "md_hasan@x.com", "grants": {}},
        ],
        "page": {"hasMore": False},
    },
]


class FakeTransport:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.fail = fail

    async def request(self, method: str, url: str, params: Any = None) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("403")
        cursor = (params or {}).get("cursor")
        self.calls.append((url, cursor))
        return PAGES[0] if cursor is None else PAGES[1]


class FakeScopes:
    def __init__(self, fail: bool) -> None:
        self._transport = FakeTransport(fail)
        self._base = "https://memory.example.com/api/v1/ctx/scopes"


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.scopes = FakeScopes(fail)


async def test_lists_humans_named_by_email_across_pages() -> None:
    client = FakeClient()

    people = await AgentMemoryPeople(client).list()  # type: ignore[arg-type]

    assert people == [
        MemoryPerson(email="arun.das@x.com", name="Arun Das", grants={"memory:read": ["/*"]}),
        MemoryPerson(email="md_hasan@x.com", name="Md Hasan"),
    ]
    assert client.scopes._transport.calls == [
        ("https://memory.example.com/api/v1/ctx/principals", None),
        ("https://memory.example.com/api/v1/ctx/principals", "c1"),
    ]


async def test_a_failed_listing_is_unavailable() -> None:
    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryPeople(FakeClient(fail=True)).list()  # type: ignore[arg-type]
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredPeople().list()


def test_name_from_email() -> None:
    assert name_from("stephen.howard@x.com") == "Stephen Howard"
    assert name_from("vidyul+test@x.com") == "Vidyul Test"
