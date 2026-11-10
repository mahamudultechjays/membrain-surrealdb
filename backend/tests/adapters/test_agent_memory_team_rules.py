from types import SimpleNamespace
from typing import Any

from app.adapters.agent_memory.team_rules import AgentMemoryTeamRules

TEAM = "org/spreetail/team/common"


class Client:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def remember(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        attr = SimpleNamespace(id="attribute:w66h")
        return SimpleNamespace(extraction=SimpleNamespace(attributes=[attr]))


class Keys:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.grants: dict[str, list[str]] = {}

    async def client_for(self, holder: str, grants: dict[str, list[str]]) -> Client:
        self.grants = grants
        return self.client


async def test_team_rule_write_uses_team_scope_key_and_returns_id() -> None:
    client = Client()
    keys = Keys(client)
    writer = AgentMemoryTeamRules(object(), lambda k: object(), scope=f"/{TEAM}/")  # type: ignore[arg-type,return-value]
    writer._keys = keys  # type: ignore[assignment]
    ref = await writer.write(
        entity_type="organization",
        entity="Cobalt Ridge",
        key="return_window",
        value="30 days",
        labels=["kind=rule"],
    )
    assert ref == "w66h"
    assert keys.grants == {"memory:read": [TEAM], "memory:write": [TEAM]}
    assert client.kwargs["scopes"] == [TEAM]
    assert client.kwargs["labels"] == ["kind=rule"]
    assert client.kwargs["memory_category"] == "knowledge"
    assert client.kwargs["triples"] == [
        {
            "entity": {"name": "Cobalt Ridge", "type": "organization"},
            "key": "return_window",
            "value": "30 days",
        }
    ]


class DictClient(Client):
    """As the live SDK answered on 10 Nov: attributes are plain dicts."""

    def __init__(self, attributes: list[dict[str, Any]], listed: list[dict[str, Any]]) -> None:
        super().__init__()
        self.attributes = attributes
        self.listed = listed
        self._base = "/ctx"
        self._transport = self

    async def remember(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(extraction=SimpleNamespace(attributes=self.attributes))

    async def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        return {"attributes": self.listed, "page": {"hasMore": False}}


def writer_for(client: Client) -> AgentMemoryTeamRules:
    writer = AgentMemoryTeamRules(object(), lambda k: object(), scope=TEAM)  # type: ignore[arg-type,return-value]
    writer._keys = Keys(client)  # type: ignore[assignment]
    return writer


ARGS = {
    "entity_type": "organization",
    "entity": "Fernway Ceramics",
    "key": "lead_time",
    "value": "14 days",
    "labels": ["kind=rule"],
}


async def test_attribute_returned_as_a_dict_is_read() -> None:
    client = DictClient([{"id": "qf61e63i7fr82r7bo7lw", "key": "lead_time"}], [])
    assert await writer_for(client).write(**ARGS) == "qf61e63i7fr82r7bo7lw"  # type: ignore[arg-type]


async def test_an_identical_rule_already_stored_is_found_in_the_team_scope() -> None:
    listed = [
        {
            "id": "other",
            "entity": "entity:organisation/fernway_ceramics",
            "key": "lead_time",
            "value": "21 days",
            "scope": [[f"{TEAM}/"]],
        },
        {
            "id": "qf61e63i7fr82r7bo7lw",
            "entity": "entity:organisation/fernway_ceramics",
            "key": "lead_time",
            "value": "14 days",
            "scope": [[f"{TEAM}/"]],
        },
    ]
    client = DictClient([], listed)
    assert await writer_for(client).write(**ARGS) == "qf61e63i7fr82r7bo7lw"  # type: ignore[arg-type]


async def test_nothing_stored_and_nothing_found_is_an_error() -> None:
    import pytest

    from app.domain.errors import MemoryUnavailableError

    with pytest.raises(MemoryUnavailableError):
        await writer_for(DictClient([], [])).write(**ARGS)  # type: ignore[arg-type]
