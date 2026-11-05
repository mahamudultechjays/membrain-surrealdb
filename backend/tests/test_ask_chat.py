import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.composition import get_chat_sessions, get_memory_chat, get_memory_recall
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_chat import ChatAccess, ChatCitation, ChatReply
from app.domain.ports.memory_recall import RecallHit, RecallResult
from app.main import app
from app.services.access import AccessService
from app.services.chat_flow import ChatSessions
from tests.conftest import sign_in

ORG, OPS = "org/spreetail", "org/spreetail/team/ops"
PRIYA, ARUN = "org/spreetail/user/priya_shah", "org/spreetail/user/arun_das"


class FakeRecall:
    """The per-layer search chat runs alongside: hits per lens, recorded by lens."""

    def __init__(self) -> None:
        self.by_lens: dict[str, list[RecallHit]] = {
            ORG: [RecallHit("attribute:a1", "Acme lead time 18", "attribute", 0.5)]
        }
        self.lenses: list[str] = []
        self.error: Exception | None = None

    async def recall(self, query: str, *, lens: str, k: int) -> RecallResult:
        self.lenses.append(lens)
        if self.error:
            raise self.error
        return RecallResult(hits=self.by_lens.get(lens, []))


class FakeChat:
    """Records (message, access, session_id); answers with one citation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ChatAccess, str | None]] = []
        self.error: Exception | None = None
        self.next_session = 0

    async def chat(self, message: str, *, access: ChatAccess, session_id: str | None) -> ChatReply:
        self.calls.append((message, access, session_id))
        if self.error:
            raise self.error
        if session_id is None:
            self.next_session += 1
        return ChatReply(
            reply="Lead time is 18 days [S1].",
            session_id=session_id or f"sess{self.next_session}",
            trace_id="tr1",
            citations=[ChatCitation("S1", "attribute:a1", "attribute", "Acme lead time 18", 0.5)],
            facts_saved=2,
        )


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
def recall() -> FakeRecall:
    return FakeRecall()


@pytest.fixture
def client(access: AccessService, chat: FakeChat, recall: FakeRecall) -> Iterator[TestClient]:
    sessions = ChatSessions()
    app.dependency_overrides[get_memory_chat] = lambda: chat
    app.dependency_overrides[get_memory_recall] = lambda: recall
    app.dependency_overrides[get_chat_sessions] = lambda: sessions
    with TestClient(app) as test_client:
        sign_in(test_client, "arun.das@x.com", "Arun Das")
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _chat(client: TestClient, **body: Any) -> Any:
    response = client.post("/api/v1/ask/chat", json={"message": "lead time?", **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_reads_every_granted_scope_and_writes_to_the_personal_one(
    client: TestClient, chat: FakeChat
) -> None:
    body = _chat(client)

    [(message, access, session_id)] = chat.calls
    assert message == "lead time?"
    assert access == ChatAccess(owner="priya.shah@x.com", read=(ORG, PRIYA), write=PRIYA)
    assert session_id is None
    assert body["scopes"] == [ORG, PRIYA]


def test_never_reads_another_users_personal_scope(client: TestClient, chat: FakeChat) -> None:
    _chat(client)

    [(_, access, _)] = chat.calls
    assert ARUN not in access.read


def test_a_team_grant_is_read_too(
    client: TestClient, chat: FakeChat, access: AccessService
) -> None:
    asyncio.run(access.grant("priya.shah@x.com", "Priya Shah", OPS, "read", "team"))

    _chat(client)

    assert chat.calls[0][1].read == (ORG, OPS, PRIYA)


def test_scopes_narrow_what_is_read(client: TestClient, chat: FakeChat) -> None:
    body = _chat(client, scopes=[ORG])

    assert chat.calls[0][1].read == (ORG,)
    assert chat.calls[0][1].write == PRIYA
    assert body["scopes"] == [ORG]


def test_unreadable_scope_is_403(client: TestClient, chat: FakeChat) -> None:
    response = client.post("/api/v1/ask/chat", json={"message": "x", "scopes": [ARUN]})

    assert response.status_code == 403
    assert chat.calls == []


def test_reply_citations_and_session_are_returned(client: TestClient) -> None:
    body = _chat(client)

    assert body["reply"] == "Lead time is 18 days [S1]."
    assert body["session_id"] == "sess1"
    assert body["trace_id"] == "tr1"
    assert body["facts_saved"] == 2
    assert body["citations"] == [
        {
            "marker": "S1",
            "id": "attribute:a1",
            "kind": "attribute",
            "snippet": "Acme lead time 18",
            "score": 0.5,
            "document_title": None,
            "position_percent": None,
            "role": None,
            "occurred_at": None,
            "layer": "org",
            "scope": ORG,
        }
    ]


def test_follow_up_continues_the_users_own_session(client: TestClient, chat: FakeChat) -> None:
    first = _chat(client)

    _chat(client, session_id=first["session_id"])

    assert chat.calls[1][2] == "sess1"


def test_someone_elses_session_is_404(client: TestClient, chat: FakeChat) -> None:
    priyas = _chat(client)["session_id"]
    sign_in(client, "arun.das@x.com", "Arun Das")

    response = client.post(
        "/api/v1/ask/chat", json={"message": "what did she ask?", "session_id": priyas}
    )

    assert response.status_code == 404
    assert len(chat.calls) == 1


def test_unknown_session_is_404(client: TestClient, chat: FakeChat) -> None:
    response = client.post("/api/v1/ask/chat", json={"message": "x", "session_id": "made-up"})

    assert response.status_code == 404
    assert chat.calls == []


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_memory_failure_is_503(client: TestClient, chat: FakeChat, error: Exception) -> None:
    chat.error = error

    assert client.post("/api/v1/ask/chat", json={"message": "x"}).status_code == 503


def test_empty_message_is_422(client: TestClient) -> None:
    assert client.post("/api/v1/ask/chat", json={"message": ""}).status_code == 422


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.post("/api/v1/ask/chat", json={"message": "x"}).status_code == 401


def test_each_citation_is_tagged_with_the_layer_it_came_from(
    client: TestClient, recall: FakeRecall
) -> None:
    body = _chat(client)

    [citation] = body["citations"]
    assert (citation["layer"], citation["scope"]) == ("org", ORG)
    assert sorted(recall.lenses) == sorted([ORG, PRIYA])


def test_a_citation_no_layer_returned_stays_untagged(
    client: TestClient, recall: FakeRecall
) -> None:
    recall.by_lens = {}

    [citation] = _chat(client)["citations"]

    assert (citation["layer"], citation["scope"]) == (None, None)


def test_a_failing_layer_search_does_not_fail_the_chat(
    client: TestClient, recall: FakeRecall
) -> None:
    recall.error = MemoryUnavailableError("down")

    body = _chat(client)

    assert body["reply"] == "Lead time is 18 days [S1]."
    assert body["citations"][0]["layer"] is None


def test_layer_search_covers_only_the_chosen_scopes(client: TestClient, recall: FakeRecall) -> None:
    _chat(client, scopes=[PRIYA])

    assert recall.lenses == [PRIYA]
