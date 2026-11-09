from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError
from surrealdb_memory._models.memory import RecallResponse

from app.adapters.agent_memory import AgentMemoryRecall, NotConfiguredRecall
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError


class FakeClient:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response or {}
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def recall(self, query: str, **kwargs: Any) -> RecallResponse:
        self.calls.append((query, kwargs))
        if self.error:
            raise self.error
        return RecallResponse.from_dict(self.response)


async def test_recall_reads_only_the_lenses() -> None:
    client = FakeClient(
        {
            "tier": "hybrid",
            "queryMs": 12,
            "trace": {"traceId": "tr1"},
            "hits": [{"id": "c1", "score": 0.7, "source": "chunk", "text": "30 days"}],
        }
    )

    result = await AgentMemoryRecall(client).recall(  # type: ignore[arg-type]
        "returns?", lenses=("org", "org/team/ops"), k=20
    )

    assert client.calls == [
        ("returns?", {"k": 20, "lens": ["org", "org/team/ops"], "include": ["facts", "passages"]})
    ]
    assert result.hits[0].kind == "chunk"
    assert (result.tier, result.query_ms, result.trace_id) == ("hybrid", 12, "tr1")


async def test_recall_failure_is_unavailable() -> None:
    client = FakeClient(error=MemoryAuthError(403, "no grant"))

    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryRecall(client).recall("q", lenses=["org"], k=1)  # type: ignore[arg-type]


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredRecall().recall("q", lenses=["org"], k=1)
