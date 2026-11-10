from typing import Any

import pytest

from app.adapters.agent_memory import AgentMemoryFactLister, NotConfiguredFactLister
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError

ME = "org/spreetail/user/mahamudul_hasan"

# Shapes as Agent Memory returned them live on 2026-11-06.
PAGE: dict[str, Any] = {
    "attributes": [
        {
            "id": "nfvnpp1sc3jqc0zvgetv",
            "entity": "entity:company/company/supidtest_zeta",
            "key": "pays",
            "value": "Net 45 terms",
            "summary": "Supidtest Zeta's pays is Net 45 terms",
            "scope": [[f"{ME}/"]],
            "supersedes": "attribute:tr66d23f7ce5f9ogznn2",
        },
        {
            "id": "attribute:bot6enmr08deq1tjjx8t",
            "entity": "['organisation', 'gatetest_omega']",
            "key": "pays",
            "value": "Net 60 terms",
            "scope": [[f"{ME}/"], [f"{ME}/"]],
        },
        {"id": "", "key": "broken"},
    ],
    "page": {"nextCursor": "c2", "hasMore": True},
}


class FakeTransport:
    def __init__(self, body: Any) -> None:
        self.body = body
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.error: Exception | None = None

    async def request(self, method: str, path: str, params: dict[str, Any]) -> Any:
        self.calls.append((method, path, params))
        if self.error:
            raise self.error
        return self.body


class FakeClient:
    def __init__(self, transport: FakeTransport) -> None:
        self._transport = transport
        self._base = "/api/v1/ctx"


class FakeKeys:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.grants: list[dict[str, list[str]]] = []
        self.closed = False

    async def client_for(self, holder: str, grants: dict[str, list[str]]) -> FakeClient:
        self.grants.append(grants)
        return self.client

    async def close(self) -> None:
        self.closed = True


def _lister(body: Any) -> tuple[AgentMemoryFactLister, FakeKeys, FakeTransport]:
    transport = FakeTransport(body)
    keys = FakeKeys(FakeClient(transport))
    lister = AgentMemoryFactLister(object(), lambda key: object())  # type: ignore[arg-type,return-value]
    lister._keys = keys  # type: ignore[assignment]
    return lister, keys, transport


async def test_lists_facts_with_a_key_for_exactly_the_tagged_scopes() -> None:
    lister, keys, transport = _lister(PAGE)

    page = await lister.page([ME, "org/a"], limit=200, cursor="c1")

    assert keys.grants == [{"memory:read": ["org/a", ME]}]
    assert transport.calls == [("GET", "/api/v1/ctx/attributes", {"limit": 200, "cursor": "c1"})]
    assert page.cursor == "c2"
    first, second = page.facts
    assert first.id == "nfvnpp1sc3jqc0zvgetv"
    assert first.text == "Supidtest Zeta's pays is Net 45 terms"
    assert first.scopes == (ME,)
    assert first.supersedes == "tr66d23f7ce5f9ogznn2"
    assert second.id == "bot6enmr08deq1tjjx8t"
    assert second.text == "gatetest omega pays Net 60 terms"
    assert second.supersedes is None


async def test_last_page_has_no_cursor_and_no_scopes_lists_nothing() -> None:
    lister, keys, transport = _lister({"attributes": [], "page": {"hasMore": False}})

    last = await lister.page([ME], limit=10, cursor=None)
    nothing = await lister.page([], limit=10, cursor=None)

    assert last.cursor is None
    assert last.facts == []
    assert transport.calls[0][2] == {"limit": 10}
    assert nothing.facts == []
    assert len(keys.grants) == 1


async def test_listing_errors_become_memory_unavailable() -> None:
    lister, keys, transport = _lister(PAGE)
    transport.error = RuntimeError("502")

    with pytest.raises(MemoryUnavailableError):
        await lister.page([ME], limit=10, cursor=None)
    await lister.close()
    assert keys.closed


async def test_not_configured() -> None:
    lister = NotConfiguredFactLister()
    with pytest.raises(MemoryNotConfiguredError):
        await lister.page([ME], limit=10, cursor=None)
    await lister.close()


async def test_listing_keeps_entity_key_value_and_source_kind() -> None:
    body = {
        "attributes": [
            {
                **PAGE["attributes"][0],
                "createdAt": "2026-11-05T07:05:06Z",
                "source": {"kind": "upsert"},
            },
            {**PAGE["attributes"][1], "source": {"kind": "turn", "ref": "turn:t1"}},
        ],
        "page": {"hasMore": False},
    }
    lister, _, _ = _lister(body)
    first, second = (await lister.page([ME], limit=10, cursor=None)).facts
    assert (first.entity_type, first.entity, first.key, first.value) == (
        "company", "supidtest_zeta", "pays", "Net 45 terms",
    )  # fmt: skip
    assert (first.created_at, first.source_kind) == ("2026-11-05T07:05:06Z", "upsert")
    assert (second.entity_type, second.entity, second.source_kind) == (
        "organisation", "gatetest_omega", "turn",
    )  # fmt: skip
