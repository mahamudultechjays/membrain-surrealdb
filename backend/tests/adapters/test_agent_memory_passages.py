from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError

from app.adapters.agent_memory import AgentMemoryPassages, NotConfiguredPassages
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError


class FakeClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def remember(self, text: str, **kwargs: Any) -> None:
        self.calls.append((text, kwargs))
        if self.error:
            raise self.error


async def test_write_stores_the_text_without_extraction() -> None:
    client = FakeClient()

    await AgentMemoryPassages(client).write("VCT node [sc4] Store Inventory.", "org/x")  # type: ignore[arg-type]

    assert client.calls == [
        ("VCT node [sc4] Store Inventory.", {"infer": "none", "scopes": ["org/x"]})
    ]


async def test_write_failure_is_unavailable() -> None:
    client = FakeClient(MemoryAuthError(403, "no grant"))

    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryPassages(client).write("t", "org/x")  # type: ignore[arg-type]


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredPassages().write("t", "org/x")
