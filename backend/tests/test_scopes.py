from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_active_scopes, get_scope_directory
from app.main import app
from app.services.scopes import ActiveScopes, ScopeDirectory

PRIYA, ARUN, DEENA = "org/user/u-0001", "org/user/u-0002", "org/user/u-0003"


@pytest.fixture
def active() -> ActiveScopes:
    return ActiveScopes([PRIYA])


@pytest.fixture
def client(active: ActiveScopes) -> Iterator[TestClient]:
    directory = ScopeDirectory()
    app.dependency_overrides[get_active_scopes] = lambda: active
    app.dependency_overrides[get_scope_directory] = lambda: directory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_shows_users_and_reads_but_no_keys(client: TestClient) -> None:
    body = client.get("/api/v1/scopes/list").json()

    assert body["active_scopes"] == [PRIYA]
    assert [s["name"] for s in body["scopes"]] == ["Priya", "Arun", "Deena"]
    assert body["scopes"][0] == {
        "id": PRIYA,
        "name": "Priya",
        "type": "user",
        "team": "org/team/ops",
        "reads": ["org", "org/team/ops", PRIYA],
    }
    assert "api_key" not in str(body)


def test_switch_sets_active_scopes(client: TestClient, active: ActiveScopes) -> None:
    response = client.post("/api/v1/scopes/switch", json={"scopes": [PRIYA, DEENA, PRIYA]})

    assert response.status_code == 200
    assert response.json() == {
        "active_scopes": [PRIYA, DEENA],
        "previous_scopes": [PRIYA],
        "message": "Scope context switched (Priya + Deena)",
    }
    assert active.get() == [PRIYA, DEENA]
    assert client.get("/api/v1/scopes/active").json()["message"] == "Acting as Priya + Deena"


@pytest.mark.parametrize("scopes", [[], ["org/user/nobody"]])
def test_switch_rejects_empty_or_unknown(
    client: TestClient, active: ActiveScopes, scopes: list[str]
) -> None:
    response = client.post("/api/v1/scopes/switch", json={"scopes": scopes})

    assert response.status_code == 422
    assert active.get() == [PRIYA]
