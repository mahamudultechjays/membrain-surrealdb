from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError

from app.adapters.agent_memory import (
    AgentMemoryFactProvenance,
    AgentMemoryRecall,
    NotConfiguredFactProvenance,
    NotConfiguredRecall,
)
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.fact_provenance import FactProvenance


class FakeTransport:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response or {}
        self.error = error
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def request(self, method: str, path: str, json: Any = None, **_: Any) -> Any:
        self.calls.append((method, path, json))
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    """Only what the adapters touch: the raw transport and the context base path."""

    def __init__(self, transport: FakeTransport) -> None:
        self._transport = transport
        self._base = "/api/v1/ctx"


async def test_recall_reads_only_the_lens() -> None:
    transport = FakeTransport(
        {
            "tier": "hybrid",
            "queryMs": 12,
            "trace": {"traceId": "tr1"},
            "hits": [{"id": "c1", "score": 0.7, "source": "chunk", "text": "30 days"}],
        }
    )

    result = await AgentMemoryRecall(FakeClient(transport)).recall(  # type: ignore[arg-type]
        "returns?", lens="org", k=20
    )

    assert transport.calls == [
        (
            "POST",
            "/api/v1/ctx/query",
            {"query": "returns?", "k": 20, "lens": [["org"]], "include": ["facts", "passages"]},
        )
    ]
    assert result.hits[0].kind == "chunk"
    assert result.hits[0].entity_type is None
    assert (result.tier, result.query_ms, result.trace_id) == ("hybrid", 12, "tr1")


async def test_recall_keeps_the_attribute_resource_and_occurred_at() -> None:
    transport = FakeTransport(
        {
            "hits": [
                {
                    "id": "attribute:a1",
                    "score": 0.5,
                    "source": "attribute",
                    "text": "Lumen Desk Lamp's return window is 30 days",
                    "resource": {
                        "kind": "attribute",
                        "entityType": "product",
                        "name": "lumen_desk_lamp",
                        "key": "return_window",
                    },
                },
                {
                    "id": "memory_chunk:m1",
                    "score": 0.38,
                    "source": "memory_chunk",
                    "text": "Pine Bench cartons hold 6 units each.",
                    "occurredAt": "2026-11-09T08:33:06Z",
                },
            ]
        }
    )

    result = await AgentMemoryRecall(FakeClient(transport)).recall(  # type: ignore[arg-type]
        "q", lens="org", k=5
    )

    attribute, chunk = result.hits
    assert (attribute.entity_type, attribute.entity_name, attribute.key) == (
        "product",
        "lumen_desk_lamp",
        "return_window",
    )
    assert chunk.occurred_at == "2026-11-09T08:33:06Z"
    assert chunk.entity_type is None


async def test_recall_failure_is_unavailable() -> None:
    transport = FakeTransport(error=MemoryAuthError(403, "no grant"))

    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryRecall(FakeClient(transport)).recall(  # type: ignore[arg-type]
            "q", lens="org", k=1
        )


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredRecall().recall("q", lens="org", k=1)


async def test_provenance_reads_trust_and_confidence_per_attribute() -> None:
    transport = FakeTransport(
        {
            "entity": {"name": "lumen_desk_lamp"},
            "attributes": [
                {
                    "id": "a1",
                    "key": "return_window",
                    "value": "30 days",
                    "confidence": 0.95,
                    "source": {"kind": "upsert", "trust": 0.95},
                    "createdAt": "2026-11-09T08:32:50Z",
                    "supersededBy": None,
                },
                {
                    "id": "a2",
                    "key": "return_window",
                    "value": "60 days",
                    "confidence": 0.6,
                    "source": {"kind": "turn", "trust": 0.5},
                    "createdAt": "2026-11-09T08:32:57Z",
                    "supersededBy": "a3",
                },
            ],
        }
    )

    out = await AgentMemoryFactProvenance(FakeClient(transport)).attributes(  # type: ignore[arg-type]
        "product", "lumen desk/lamp"
    )

    assert transport.calls[0][:2] == ("GET", "/api/v1/ctx/entities/product/lumen%20desk%2Flamp")
    assert out["a1"] == FactProvenance(
        trust=0.95, confidence=0.95, source_kind="upsert", created_at="2026-11-09T08:32:50Z"
    )
    assert (out["a2"].trust, out["a2"].source_kind, out["a2"].superseded_by) == (
        0.5,
        "turn",
        "a3",
    )


async def test_provenance_failure_is_unavailable() -> None:
    transport = FakeTransport(error=MemoryAuthError(403, "no"))

    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryFactProvenance(FakeClient(transport)).attributes(  # type: ignore[arg-type]
            "product", "x"
        )


async def test_provenance_not_configured_is_empty() -> None:
    assert await NotConfiguredFactProvenance().attributes("product", "x") == {}
