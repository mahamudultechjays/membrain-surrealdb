from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError
from surrealdb_memory._models.memory import RememberResponse

from app.adapters.agent_memory import AgentMemoryCapture, NotConfiguredCapture
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_capture import FactTriple

# Shape of a real `infer: "preview"` response, trimmed.
PREVIEW = {
    "mode": "preview",
    "sessionId": "s1",
    "preview": True,
    "extraction": {
        "turnId": "",
        "entities": [
            {
                "id": "",
                "name": "Acme Logistics",
                "entityType": "organisation",
                "memoryCategory": "context",
                "isNew": True,
            },
        ],
        "attributes": [
            {
                "id": "",
                "entityId": "",
                "key": "lead_time",
                "value": "18 days",
                "memoryCategory": "context",
            },
        ],
        "relations": [
            {
                "subject": "Acme Logistics",
                "label": "ships_to",
                "object": "Reno warehouse",
                "memoryCategory": "context",
            },
        ],
        "instructions": [{"id": "", "label": "bullets", "description": "Use bullets."}],
        "uncertainties": [{"about": "returns", "reason": "hedged"}],
        "corrections": [{"key": "lead_time", "from": "10 days"}],
    },
}

# A stored write carries ids, so attributes can be tied to their entity.
STORED = {
    "mode": "full",
    "sessionId": "s2",
    "turnId": "t1",
    "extraction": {
        "entities": [
            {
                "id": "e1",
                "name": "Acme Logistics",
                "entityType": "organisation",
                "memoryCategory": "context",
                "isNew": False,
            }
        ],
        "attributes": [
            {
                "id": "a1",
                "entityId": "e1",
                "key": "lead_time",
                "value": "18 days",
                "memoryCategory": "context",
            }
        ],
    },
}


class FakeClient:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[str | None, str | None]] = []
        self.kwargs: dict[str, Any] = {}

    async def remember(
        self, text: str | None, *, infer: str | None = None, **kwargs: Any
    ) -> RememberResponse:
        self.calls.append((text, infer))
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return RememberResponse.from_dict(self.response)


async def test_preview_maps_every_section() -> None:
    client = FakeClient(PREVIEW)

    result = await AgentMemoryCapture(client).preview("text")  # type: ignore[arg-type]

    assert client.calls == [("text", "preview")]
    assert result.mode == "preview"
    assert result.turn_id is None
    assert result.entities[0].name == "Acme Logistics"
    assert result.entities[0].is_new is True
    assert result.attributes[0].entity is None  # preview leaves entityId empty
    assert result.relations[0].object == "Reno warehouse"
    assert result.instructions[0].label == "bullets"
    assert result.uncertainties[0].about == "returns"
    assert result.corrections == ['{"from": "10 days", "key": "lead_time"}']


async def test_store_uses_full_extraction_and_resolves_entities() -> None:
    client = FakeClient(STORED)

    result = await AgentMemoryCapture(client).store("text")  # type: ignore[arg-type]

    assert client.calls == [("text", "full")]
    assert result.mode == "stored"
    assert result.turn_id == "t1"
    assert result.attributes[0].entity == "Acme Logistics"
    assert result.attributes[0].id == "a1"


async def test_scope_is_sent_as_write_region() -> None:
    client = FakeClient(PREVIEW)

    await AgentMemoryCapture(client).preview("text", "org/user/u-0001")  # type: ignore[arg-type]

    assert client.kwargs["scopes"] == ["org/user/u-0001"]


async def test_store_facts_sends_triples_without_text() -> None:
    client = FakeClient(STORED)
    fact = FactTriple("Acme Logistics", "organisation", "lead_time", "18 days", "knowledge")

    result = await AgentMemoryCapture(client).store_facts(  # type: ignore[arg-type]
        [fact], "org/user/u-0001"
    )

    assert client.calls == [(None, "triples")]
    assert client.kwargs == {
        "scopes": ["org/user/u-0001"],
        "triples": [
            {
                "entity": {"type": "organisation", "name": "Acme Logistics"},
                "key": "lead_time",
                "value": "18 days",
                "memory_category": "knowledge",
            }
        ],
    }
    assert result.mode == "stored"


async def test_no_extraction_gives_empty_result() -> None:
    client = FakeClient({"mode": "none", "sessionId": "s3"})

    result = await AgentMemoryCapture(client).preview("text")  # type: ignore[arg-type]

    assert result.session_id == "s3"
    assert result.entities == []


async def test_failures_become_unavailable() -> None:
    client = FakeClient(error=MemoryAuthError(401, "bad key"))

    with pytest.raises(MemoryUnavailableError):
        await AgentMemoryCapture(client).preview("text")  # type: ignore[arg-type]


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredCapture().preview("text")
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredCapture().store("text")
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredCapture().store_facts([], "org/user/u-0001")
