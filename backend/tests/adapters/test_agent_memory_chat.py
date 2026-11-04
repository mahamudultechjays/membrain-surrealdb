from typing import Any

import pytest
from surrealdb_memory import MemoryAuthError

from app.adapters.agent_memory import AgentMemoryChat, NotConfiguredChat
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_chat import ChatAccess, ChatCitation

BASE = "/api/v1/ctx"
ORG, ME = "org/spreetail", "org/spreetail/user/vidyul_narayanan"
ACCESS = ChatAccess(owner="vidyul@x.com", read=(ORG, ME), write=ME)

REPLY = {
    "reply": "Lead time is 18 days [S1], see the manual [S2].",
    "sessionId": "sess1",
    "traceId": "tr1",
    "memoryUpdates": {"entities": [{}], "attributes": [{}, {}], "relations": []},
    "citations": [
        {
            "marker": "S1",
            "id": "attribute:a1",
            "kind": "attribute",
            "snippet": "Acme lead time is 18 days",
            "score": 0.49,
        },
        {
            "marker": "S2",
            "id": "chunk:c1",
            "kind": "chunk",
            "snippet": "Section 4",
            "score": 0.3,
            "documentTitle": "Ops manual",
            "positionPercent": 40.5,
            "role": "user",
            "occurredAt": "2026-11-04T10:00:00Z",
        },
    ],
}


class FakeTransport:
    """Records (method, path, json) and answers by path."""

    def __init__(self, log: list[tuple[str, str, Any]], name: str) -> None:
        self.log = log
        self.name = name
        self.chat_error: Exception | None = None
        self.mint_error: Exception | None = None
        self.minted = 0

    async def request(self, method: str, path: str, *, json: Any = None, **_: Any) -> Any:
        self.log.append((self.name, f"{method} {path.removeprefix(BASE)}", json))
        if path.endswith("/keys"):
            if self.mint_error:
                raise self.mint_error
            self.minted += 1
            return {"id": f"k{self.minted}", "key": f"secret-{self.minted}"}
        if path.endswith("/chat"):
            if self.chat_error:
                raise self.chat_error
            return REPLY
        return {}


class FakeClient:
    def __init__(self, log: list[tuple[str, str, Any]], name: str) -> None:
        self._base = BASE
        self._transport = FakeTransport(log, name)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class Setup:
    def __init__(self) -> None:
        self.log: list[tuple[str, str, Any]] = []
        self.admin = FakeClient(self.log, "admin")
        self.users: dict[str, FakeClient] = {}
        self.chat = AgentMemoryChat(self.admin, self.connect)  # type: ignore[arg-type]

    def connect(self, key: str) -> FakeClient:
        self.users[key] = FakeClient(self.log, key)
        return self.users[key]

    def calls(self, who: str, prefix: str) -> list[Any]:
        return [body for name, call, body in self.log if name == who and call.startswith(prefix)]


@pytest.fixture
def setup() -> Setup:
    return Setup()


async def test_chat_goes_through_a_key_minted_for_the_users_grants(setup: Setup) -> None:
    await setup.chat.chat("lead time?", access=ACCESS, session_id=None)

    [mint] = setup.calls("admin", "POST /keys")
    assert mint["grants"] == {"memory:read": [ORG, ME], "memory:write": [ME]}
    assert setup.calls("admin", "POST /chat") == []
    assert setup.calls("secret-1", "POST /chat") == [{"message": "lead time?", "scopes": [[ME]]}]


async def test_session_id_is_passed_on(setup: Setup) -> None:
    await setup.chat.chat("and before?", access=ACCESS, session_id="sess1")

    [body] = setup.calls("secret-1", "POST /chat")
    assert body["sessionId"] == "sess1"


async def test_key_is_reused_while_access_is_unchanged(setup: Setup) -> None:
    await setup.chat.chat("one", access=ACCESS, session_id=None)
    await setup.chat.chat("two", access=ACCESS, session_id=None)

    assert len(setup.calls("admin", "POST /keys")) == 1
    assert len(setup.calls("secret-1", "POST /chat")) == 2


async def test_changed_access_mints_a_new_key_and_deletes_the_old(setup: Setup) -> None:
    await setup.chat.chat("one", access=ACCESS, session_id=None)
    narrower = ChatAccess(owner=ACCESS.owner, read=(ME,), write=ME)

    await setup.chat.chat("two", access=narrower, session_id=None)

    [first, second] = setup.calls("admin", "POST /keys")
    assert second["grants"]["memory:read"] == [ME]
    assert [call for _, call, _ in setup.log if call.startswith("DELETE /keys/")] == [
        f"DELETE /keys/{first['name']}"
    ]
    assert setup.users["secret-1"].closed
    assert setup.calls("secret-2", "POST /chat")


async def test_each_owner_gets_their_own_key(setup: Setup) -> None:
    other = ChatAccess(owner="arun@x.com", read=(ORG,), write="org/spreetail/user/arun_das")

    await setup.chat.chat("one", access=ACCESS, session_id=None)
    await setup.chat.chat("two", access=other, session_id=None)

    names = [body["name"] for body in setup.calls("admin", "POST /keys")]
    assert len(set(names)) == 2
    assert not [call for _, call, _ in setup.log if call.startswith("DELETE")]


async def test_reply_carries_citations_and_saved_fact_count(setup: Setup) -> None:
    result = await setup.chat.chat("lead time?", access=ACCESS, session_id=None)

    assert (result.reply, result.session_id, result.trace_id) == (
        REPLY["reply"],
        "sess1",
        "tr1",
    )
    assert result.facts_saved == 3
    assert result.citations == [
        ChatCitation("S1", "attribute:a1", "attribute", "Acme lead time is 18 days", 0.49),
        ChatCitation(
            "S2",
            "chunk:c1",
            "chunk",
            "Section 4",
            0.3,
            document_title="Ops manual",
            position_percent=40.5,
            role="user",
            occurred_at="2026-11-04T10:00:00Z",
        ),
    ]


async def test_close_deletes_every_minted_key(setup: Setup) -> None:
    await setup.chat.chat("one", access=ACCESS, session_id=None)

    await setup.chat.close()

    assert len([call for _, call, _ in setup.log if call.startswith("DELETE /keys/")]) == 1
    assert setup.users["secret-1"].closed


async def test_mint_failure_is_unavailable(setup: Setup) -> None:
    setup.admin._transport.mint_error = MemoryAuthError(403, "no grant:manage")

    with pytest.raises(MemoryUnavailableError):
        await setup.chat.chat("q", access=ACCESS, session_id=None)


async def test_chat_failure_is_unavailable(setup: Setup) -> None:
    await setup.chat.chat("warm up", access=ACCESS, session_id=None)
    setup.users["secret-1"]._transport.chat_error = MemoryAuthError(500, "model down")

    with pytest.raises(MemoryUnavailableError):
        await setup.chat.chat("q", access=ACCESS, session_id=None)


async def test_not_configured() -> None:
    with pytest.raises(MemoryNotConfiguredError):
        await NotConfiguredChat().chat("q", access=ACCESS, session_id=None)
