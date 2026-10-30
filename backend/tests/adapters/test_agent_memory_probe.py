from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError

from app.adapters.agent_memory import AgentMemoryProbe, NotConfiguredProbe


class FakeClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def whoami(self) -> Any:
        if self.error:
            raise self.error
        return object()


async def test_ok_when_whoami_succeeds() -> None:
    assert await AgentMemoryProbe(FakeClient()).check() == "ok"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "error",
    [MemoryAuthError(401, "bad key"), ConnectionError("dns"), TimeoutError()],
)
async def test_unavailable_on_any_failure(error: Exception) -> None:
    assert await AgentMemoryProbe(FakeClient(error)).check() == "unavailable"  # type: ignore[arg-type]


async def test_not_configured_probe() -> None:
    assert await NotConfiguredProbe().check() == "not_configured"
