from collections.abc import Iterator

import pytest
from fastapi import HTTPException, Request
from pydantic import SecretStr

from app import composition
from app.api.deps import authorize_scopes
from app.core.config import settings
from app.domain.errors import UnknownScopeError
from app.services.scopes import ScopeDirectory

PRIYA, ARUN, DEENA = "org/user/u-0001", "org/user/u-0002", "org/user/u-0003"


def test_layers_are_org_team_personal() -> None:
    layers = ScopeDirectory().read_layers(PRIYA)

    assert [(layer.name, layer.path) for layer in layers] == [
        ("org", "org"),
        ("team", "org/team/ops"),
        ("personal", PRIYA),
    ]


def test_arun_cannot_read_priyas_team_or_personal_layer() -> None:
    paths = {layer.path for layer in ScopeDirectory().read_layers(ARUN)}

    assert "org/team/ops" not in paths
    assert PRIYA not in paths


def test_unknown_scope_raises() -> None:
    with pytest.raises(UnknownScopeError):
        ScopeDirectory().get("org/user/nobody")


def test_describe_joins_names() -> None:
    assert ScopeDirectory().describe([PRIYA, DEENA]) == "Priya + Deena"


def _request(caller: str | None) -> Request:
    request = Request({"type": "http", "headers": []})
    request.state.scope = caller
    return request


def test_authorize_rejects_unknown_scope() -> None:
    with pytest.raises(HTTPException) as caught:
        authorize_scopes(_request(None), ScopeDirectory(), ["org/user/nobody"])
    assert caught.value.status_code == 422


def test_authorize_rejects_other_users_scope_for_keyed_caller() -> None:
    with pytest.raises(HTTPException) as caught:
        authorize_scopes(_request(ARUN), ScopeDirectory(), [PRIYA])
    assert caught.value.status_code == 403


def test_authorize_allows_own_scope_and_unkeyed_caller() -> None:
    authorize_scopes(_request(PRIYA), ScopeDirectory(), [PRIYA])
    authorize_scopes(_request(None), ScopeDirectory(), [PRIYA, DEENA])


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENDPOINT", "https://memory.example.com")
    monkeypatch.setattr(settings, "AGENT_MEMORY_CONTEXT", "poc")
    monkeypatch.setattr(settings, "AGENT_MEMORY_API_KEY", SecretStr("shared"))
    monkeypatch.setattr(settings, "MEMBRAIN_USER_PRIYA_KEY", SecretStr("k-priya"))
    monkeypatch.setattr(settings, "MEMBRAIN_USER_ARUN_KEY", None)
    composition.get_agent_memory_client.cache_clear()
    composition._user_clients.clear()
    yield
    composition.get_agent_memory_client.cache_clear()
    composition._user_clients.clear()


@pytest.mark.usefixtures("configured")
async def test_client_for_scope_uses_user_key_else_shared() -> None:
    priya = composition.client_for_scope(PRIYA)
    arun = composition.client_for_scope(ARUN)

    assert priya is not None and priya.api_key == "k-priya"
    assert priya is composition.client_for_scope(PRIYA)
    assert arun is composition.get_agent_memory_client()

    await composition.close_clients()
    assert composition._user_clients == {}
