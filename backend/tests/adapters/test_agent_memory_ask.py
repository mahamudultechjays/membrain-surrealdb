from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError

from app.adapters.agent_memory import AgentMemoryRecall, NotConfiguredRecall
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError


class FakeTransport:
    def __init__(self, client: "FakeClient") -> None:
        self.client = client

    async def request(self, method: str, path: str, json: dict[str, Any]) -> dict[str, Any]:
        self.client.calls.append((method, path, json))
        if self.client.error:
            raise self.client.error
        return self.client.response


class FakeClient:
    """Recall goes through the raw transport: the SDK drops each hit's resource."""

    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response or {}
        self.error = error
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._transport = FakeTransport(self)
        self._base = "/api/v1/ctx"


async def test_recall_reads_only_the_lens() -> None:
    client = FakeClient(
        {
            "tier": "hybrid",
            "queryMs": 12,
            "trace": {"traceId": "tr1"},
            "hits": [
                {"id": "c1", "score": 0.7, "source": "chunk", "text": "30 days"},
                {
                    "id": "memory_chunk:m1",
                    "score": 0.6,
                    "source": "memory_chunk",
                    "text": "Returns are 30 days.",
                    "resource": {"kind": "session", "sessionId": "s1", "turnId": "t1"},
                },
            ],
        }
    )

    result = await AgentMemoryRecall(client).recall(  # type: ignore[arg-type]
        "returns?", lens="org", k=20
    )

    assert client.calls == [
        (
            "POST",
            "/api/v1/ctx/query",
            {"query": "returns?", "k": 20, "lens": ["org"], "include": ["facts", "passages"]},
        )
    ]
    assert result.hits[0].kind == "chunk"
    assert result.hits[0].turn_id is None
    assert (result.hits[1].kind, result.hits[1].turn_id) == ("memory_chunk", "t1")
    assert (result.tier, result.query_ms, result.trace_id) == ("hybrid", 12, "tr1")


async def test_recall_failure_is_unavailable() -> None:
    client = FakeClient(error=MemoryAuthError(403, "no grant"))

    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryRecall(client).recall("q", lens="org", k=1)  # type: ignore[arg-type]


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredRecall().recall("q", lens="org", k=1)
