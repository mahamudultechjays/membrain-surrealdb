import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_reflect
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_chat import ChatAccess, Reflection
from app.main import app
from app.services.access import AccessService
from tests.conftest import sign_in

ORG, OPS = "org/spreetail", "org/spreetail/team/ops"
PRIYA, ARUN = "org/spreetail/user/priya_shah", "org/spreetail/user/arun_das"
URL = "/api/v1/ask/reflect"


class FakeReflect:
    """Records (question, access); answers with two pieces of evidence."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ChatAccess]] = []
        self.error: Exception | None = None

    async def reflect(self, question: str, *, access: ChatAccess) -> Reflection:
        self.calls.append((question, access))
        if self.error:
            raise self.error
        return Reflection(
            text="Acme is the only carrier.",
            evidence=["Acme ships to Reno", "Lead time 18 days"],
            trace_id="tr1",
        )


@pytest.fixture
def reflect() -> FakeReflect:
    return FakeReflect()


@pytest.fixture
def client(access: AccessService, reflect: FakeReflect) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_reflect] = lambda: reflect
    with TestClient(app) as test_client:
        sign_in(test_client, "arun.das@x.com", "Arun Das")
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _ask(client: TestClient, **body: Any) -> Any:
    response = client.post(URL, json={"question": "What about carriers?", **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_reflects_over_every_granted_scope(client: TestClient, reflect: FakeReflect) -> None:
    body = _ask(client)

    [(question, access)] = reflect.calls
    assert question == "What about carriers?"
    assert access.owner == "priya.shah@x.com"
    assert access.read == (ORG, PRIYA)
    assert body == {
        "answer": "Acme is the only carrier.",
        "evidence": ["Acme ships to Reno", "Lead time 18 days"],
        "scopes": [ORG, PRIYA],
        "trace_id": "tr1",
    }


def test_never_reads_another_users_personal_scope(client: TestClient, reflect: FakeReflect) -> None:
    _ask(client)

    assert ARUN not in reflect.calls[0][1].read


def test_a_team_grant_is_read_too(
    client: TestClient, reflect: FakeReflect, access: AccessService
) -> None:
    asyncio.run(access.grant("priya.shah@x.com", "Priya Shah", OPS, "read", "team"))

    _ask(client)

    assert reflect.calls[0][1].read == (ORG, OPS, PRIYA)


def test_scopes_narrow_what_is_read(client: TestClient, reflect: FakeReflect) -> None:
    body = _ask(client, scopes=[PRIYA])

    assert reflect.calls[0][1].read == (PRIYA,)
    assert body["scopes"] == [PRIYA]


def test_unreadable_scope_is_403(client: TestClient, reflect: FakeReflect) -> None:
    response = client.post(URL, json={"question": "x", "scopes": [ARUN]})

    assert response.status_code == 403
    assert reflect.calls == []


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_memory_failure_is_503(client: TestClient, reflect: FakeReflect, error: Exception) -> None:
    reflect.error = error

    assert client.post(URL, json={"question": "x"}).status_code == 503


@pytest.mark.parametrize("question", ["", "   "])
def test_empty_question_is_422(client: TestClient, question: str) -> None:
    assert client.post(URL, json={"question": question}).status_code == 422


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.post(URL, json={"question": "x"}).status_code == 401
