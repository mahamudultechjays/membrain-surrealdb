from typing import Any

import pytest

from app.adapters.agent_memory import AgentMemoryScopeRegistry, NotConfiguredScopeRegistry
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError

PAGES = [
    {
        "scopes": [
            {"path": "/", "tombstonedAt": None},
            {"path": "org/", "tombstonedAt": None},
            {"path": "org/spreetail/", "tombstonedAt": None},
        ],
        "page": {"nextCursor": "c1", "hasMore": True},
    },
    {
        "scopes": [
            {"path": "org/spreetail/user/", "tombstonedAt": None},
            {"path": "org/spreetail/old/", "tombstonedAt": "2026-10-16T06:25:34Z"},
        ],
        "page": {"nextCursor": None, "hasMore": False},
    },
]


class FakeTransport:
    def __init__(self) -> None:
        self.cursors: list[str | None] = []

    async def request(self, method: str, url: str, params: Any = None) -> dict[str, Any]:
        cursor = (params or {}).get("cursor")
        self.cursors.append(cursor)
        return PAGES[0] if cursor is None else PAGES[1]


class FakeScopes:
    def __init__(self, fail: bool = False) -> None:
        self._transport = FakeTransport()
        self._base = "https://memory.example.com/api/v1/ctx/scopes"
        self.registered: list[str] = []
        self.fail = fail

    async def register(self, path: str, **_: Any) -> None:
        if self.fail:
            raise RuntimeError("403")
        self.registered.append(path)


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.scopes = FakeScopes(fail)


async def test_list_pages_through_and_skips_deleted_paths() -> None:
    client = FakeClient()

    paths = await AgentMemoryScopeRegistry(client).list("org")  # type: ignore[arg-type]

    assert paths == ["org", "org/spreetail", "org/spreetail/user"]
    assert client.scopes._transport.cursors == [None, "c1"]


async def test_ensure_registers_only_missing_parts() -> None:
    client = FakeClient()

    await AgentMemoryScopeRegistry(client).ensure("org/spreetail/user/jane_doe/")  # type: ignore[arg-type]

    assert client.scopes.registered == ["org/spreetail/user/jane_doe"]


async def test_register_failure_is_unavailable() -> None:
    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryScopeRegistry(FakeClient(fail=True)).ensure("org/new")  # type: ignore[arg-type]


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredScopeRegistry().list()
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredScopeRegistry().ensure("org")
