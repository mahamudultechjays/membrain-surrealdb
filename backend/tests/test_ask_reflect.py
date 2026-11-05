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
    """Answers per scope: the scope's own value, or no evidence if told so."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ChatAccess]] = []
        self.values = {ORG: "10%", OPS: "20%", PRIYA: "12%"}
        self.empty: set[str] = set()
        self.failing: dict[str, Exception] = {}

    async def reflect(self, question: str, *, access: ChatAccess) -> Reflection:
        self.calls.append((question, access))
        [scope] = access.read
        if scope in self.failing:
            raise self.failing[scope]
        if scope in self.empty:
            return Reflection(text="Nothing bears on this.", evidence=[], trace_id=f"tr-{scope}")
        value = self.values[scope]
        return Reflection(
            text=f"The discount is {value}.",
            evidence=[f"Harbor Basics max discount is {value}"],
            trace_id=f"tr-{scope}",
        )


@pytest.fixture
def reflect() -> FakeReflect:
    return FakeReflect()


@pytest.fixture
def client(access: AccessService, reflect: FakeReflect) -> Iterator[TestClient]:
    asyncio.run(access.grant("priya.shah@x.com", "Priya Shah", OPS, "read", "team"))
    app.dependency_overrides[get_memory_reflect] = lambda: reflect
    with TestClient(app) as test_client:
        sign_in(test_client, "arun.das@x.com", "Arun Das")
        sign_in(test_client, "priya.shah@x.com", "Priya Shah")
        yield test_client
    app.dependency_overrides.clear()


def _ask(client: TestClient, **body: Any) -> Any:
    response = client.post(URL, json={"question": "Harbor Basics discount?", **body})
    assert response.status_code == 200, response.text
    return response.json()


def _summary(body: Any) -> list[tuple[str, str, str]]:
    return [(layer["layer"], layer["scope"], layer["status"]) for layer in body["layers"]]


def test_reflects_once_per_layer_each_reading_only_that_scope(
    client: TestClient, reflect: FakeReflect
) -> None:
    _ask(client)

    assert sorted(access.read for _, access in reflect.calls) == [(ORG,), (OPS,), (PRIYA,)]
    # Each scope gets its own key holder, so each key reads only that scope.
    assert len({access.owner for _, access in reflect.calls}) == 3


def test_org_applies_and_the_rest_are_overridden(client: TestClient) -> None:
    body = _ask(client)

    assert _summary(body) == [
        ("org", ORG, "applies"),
        ("team", OPS, "overridden"),
        ("personal", PRIYA, "overridden"),
    ]
    assert body["applies"] == ORG
    assert body["layers"][0]["answer"] == "The discount is 10%."
    assert body["layers"][1]["evidence"] == ["Harbor Basics max discount is 20%"]


def test_a_layer_with_no_evidence_passes_precedence_down(
    client: TestClient, reflect: FakeReflect
) -> None:
    reflect.empty = {ORG}

    body = _ask(client)

    assert _summary(body) == [
        ("org", ORG, "empty"),
        ("team", OPS, "applies"),
        ("personal", PRIYA, "overridden"),
    ]
    assert body["applies"] == OPS


def test_one_failing_layer_is_reported_and_skipped(
    client: TestClient, reflect: FakeReflect
) -> None:
    reflect.failing = {ORG: MemoryUnavailableError("timeout")}

    body = _ask(client)

    assert body["layers"][0]["status"] == "failed"
    assert body["layers"][0]["error"] == "timeout"
    assert body["applies"] == OPS


def test_scopes_narrow_the_layers(client: TestClient, reflect: FakeReflect) -> None:
    body = _ask(client, scopes=[PRIYA])

    assert [access.read for _, access in reflect.calls] == [(PRIYA,)]
    assert _summary(body) == [("personal", PRIYA, "applies")]


def test_never_reads_another_users_personal_scope(client: TestClient, reflect: FakeReflect) -> None:
    _ask(client)

    assert all(ARUN not in access.read for _, access in reflect.calls)


def test_unreadable_scope_is_403(client: TestClient, reflect: FakeReflect) -> None:
    response = client.post(URL, json={"question": "x", "scopes": [ARUN]})

    assert response.status_code == 403
    assert reflect.calls == []


@pytest.mark.parametrize("error", [MemoryNotConfiguredError(), MemoryUnavailableError("down")])
def test_every_layer_failing_is_503(
    client: TestClient, reflect: FakeReflect, error: Exception
) -> None:
    reflect.failing = {ORG: error, OPS: error, PRIYA: error}

    assert client.post(URL, json={"question": "x"}).status_code == 503


@pytest.mark.parametrize("question", ["", "   "])
def test_empty_question_is_422(client: TestClient, question: str) -> None:
    assert client.post(URL, json={"question": question}).status_code == 422


def test_signed_out_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")

    assert client.post(URL, json={"question": "x"}).status_code == 401
