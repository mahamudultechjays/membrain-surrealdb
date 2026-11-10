"""The promotion team scope is read-only for people; team admins are a role."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_people, get_scope_registry
from app.main import app
from app.services.access import AccessService
from tests.conftest import FakeRegistry, sign_in

TEAM = "org/spreetail/team/common"
PRIYA = "priya.shah@x.com"


class NoPeople:
    async def list(self) -> list[object]:
        return []


@pytest.fixture
def client(access: AccessService, registry: FakeRegistry) -> Iterator[TestClient]:
    app.dependency_overrides[get_scope_registry] = lambda: registry
    app.dependency_overrides[get_memory_people] = lambda: NoPeople()
    with TestClient(app) as test_client:
        sign_in(test_client, PRIYA, "Priya Shah")
        sign_in(test_client, "admin@x.com", "Ada Admin")
        yield test_client
    app.dependency_overrides.clear()


def grant(client: TestClient, access: str) -> object:
    return client.post(
        f"/api/v1/admin/users/{PRIYA}/grants",
        json={"scope_path": TEAM, "access": access, "layer": "team"},
    )


def test_write_grant_on_team_scope_is_refused(client: TestClient) -> None:
    response = grant(client, "write")
    assert response.status_code == 400  # type: ignore[attr-defined]
    assert response.json()["detail"] == "The team scope is written only by promotion approval."  # type: ignore[attr-defined]


def test_read_grant_on_team_scope_is_allowed(client: TestClient) -> None:
    assert grant(client, "read").status_code == 201  # type: ignore[attr-defined]


def test_team_admin_role_round_trip(client: TestClient) -> None:
    assert client.put(f"/api/v1/admin/team-admins/{PRIYA}").status_code == 204
    assert client.get("/api/v1/admin/team-admins").json() == {"emails": [PRIYA]}
    sign_in(client, PRIYA, "Priya Shah")
    assert client.get("/api/v1/auth/me").json()["is_team_admin"] is True
    sign_in(client, "admin@x.com", "Ada Admin")
    assert client.delete(f"/api/v1/admin/team-admins/{PRIYA}").status_code == 204
    sign_in(client, PRIYA, "Priya Shah")
    assert client.get("/api/v1/auth/me").json()["is_team_admin"] is False


def test_team_admin_endpoints_need_org_admin(client: TestClient) -> None:
    client.put(f"/api/v1/admin/team-admins/{PRIYA}")
    sign_in(client, PRIYA, "Priya Shah")
    assert client.put("/api/v1/admin/team-admins/other@x.com").status_code == 403
