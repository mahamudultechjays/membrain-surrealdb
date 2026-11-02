import pytest
from fastapi import HTTPException, Request

from app.api.deps import authorize_scopes
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


def test_authorize_allows_known_scopes() -> None:
    authorize_scopes(_request(None), ScopeDirectory(), [PRIYA, DEENA])
