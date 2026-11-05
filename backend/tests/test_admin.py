from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_people, get_scope_registry
from app.domain.errors import MemoryUnavailableError
from app.domain.ports.memory_people import MemoryPerson
from app.main import app
from app.services.access import AccessService
from tests.conftest import FakeRegistry, sign_in

OPS = "org/spreetail/team/ops"
PRIYA_EMAIL = "priya.shah@x.com"
FULL = {"memory:read": ["/*"], "memory:write": ["/*"]}


class FakePeople:
    """Agent Memory's principals: Priya (who signed in here) and one who has not."""

    def __init__(self) -> None:
        self.error: Exception | None = None

    async def list(self) -> list[MemoryPerson]:
        if self.error:
            raise self.error
        return [
            MemoryPerson(email=PRIYA_EMAIL, name="Priya", grants={"memory:read": ["/org/*"]}),
            MemoryPerson(email="stephen.howard@x.com", name="Stephen Howard", grants=FULL),
        ]


@pytest.fixture
def people() -> FakePeople:
    return FakePeople()


@pytest.fixture
def client(
    access: AccessService, registry: FakeRegistry, people: FakePeople
) -> Iterator[TestClient]:
    app.dependency_overrides[get_scope_registry] = lambda: registry
    app.dependency_overrides[get_memory_people] = lambda: people
    with TestClient(app) as test_client:
        sign_in(test_client, PRIYA_EMAIL, "Priya Shah")
        sign_in(test_client, "admin@x.com", "Ada Admin")
        yield test_client
    app.dependency_overrides.clear()


def test_lists_users_with_their_grants(client: TestClient) -> None:
    users = {u["email"]: u for u in client.get("/api/v1/admin/users").json()["users"]}

    assert set(users) == {"admin@x.com", PRIYA_EMAIL, "stephen.howard@x.com"}
    assert users["admin@x.com"]["is_admin"] is True
    assert [g["scope_path"] for g in users[PRIYA_EMAIL]["grants"]] == [
        "org/spreetail",
        "org/spreetail/user/priya_shah",
    ]


def test_lists_agent_memory_people_who_hold_no_scopes_here_last(client: TestClient) -> None:
    body = client.get("/api/v1/admin/users").json()

    # Priya is listed once, with her grants; Stephen only Agent Memory knows.
    assert [u["email"] for u in body["users"]][-1] == "stephen.howard@x.com"
    assert body["users"][-1] == {
        "email": "stephen.howard@x.com",
        "name": "Stephen Howard",
        "is_admin": False,
        "grants": [],
        "memory_grants": FULL,
    }
    assert body["people_error"] is None
    assert body["memory_loaded"] is True


def test_each_person_carries_their_agent_memory_grants_matched_by_email(
    client: TestClient,
) -> None:
    users = {u["email"]: u for u in client.get("/api/v1/admin/users").json()["users"]}

    # Priya keeps the name she signed in with; her Agent Memory grants come along.
    assert users[PRIYA_EMAIL]["name"] == "Priya Shah"
    assert users[PRIYA_EMAIL]["memory_grants"] == {"memory:read": ["/org/*"]}
    # The admin has no principal in Agent Memory.
    assert users["admin@x.com"]["memory_grants"] is None


def test_lists_this_apps_users_when_agent_memory_people_fail(
    client: TestClient, people: FakePeople
) -> None:
    people.error = MemoryUnavailableError("down")

    response = client.get("/api/v1/admin/users")

    assert response.status_code == 200
    assert {u["email"] for u in response.json()["users"]} == {"admin@x.com", PRIYA_EMAIL}
    assert response.json()["people_error"] == "Agent Memory call failed: down"
    assert response.json()["memory_loaded"] is False


def test_grants_name_whose_space_each_scope_is(client: TestClient) -> None:
    priya_space = "org/spreetail/user/priya_shah"
    client.post(
        "/api/v1/admin/users/admin@x.com/grants",
        json={"scope_path": priya_space, "access": "read", "layer": "team"},
    )

    # The session is the admin's: they now read Priya's space through a team grant.
    owners = {g["scope_path"]: g["owner"] for g in client.get("/api/v1/auth/me").json()["grants"]}
    users = {u["email"]: u for u in client.get("/api/v1/admin/users").json()["users"]}

    assert owners == {
        "org/spreetail": None,
        "org/spreetail/user/ada_admin": "Ada Admin",
        priya_space: "Priya Shah",
    }
    assert {g["scope_path"]: g["owner"] for g in users[PRIYA_EMAIL]["grants"]} == {
        "org/spreetail": None,
        priya_space: "Priya Shah",
    }


def test_grant_then_revoke_a_team_scope(client: TestClient, registry: FakeRegistry) -> None:
    url = f"/api/v1/admin/users/{PRIYA_EMAIL}/grants"

    granted = client.post(url, json={"scope_path": OPS, "access": "read", "layer": "team"})
    revoked = client.delete(url, params={"scope_path": OPS})
    again = client.delete(url, params={"scope_path": OPS})

    assert granted.status_code == 201
    assert {"scope_path": OPS, "access": "read", "layer": "team", "owner": None} in granted.json()[
        "grants"
    ]
    assert granted.json()["name"] == "Priya Shah"
    assert registry.ensured[-1] == OPS
    assert revoked.status_code == 204
    assert again.status_code == 404


def test_grant_to_a_user_who_has_not_signed_in_yet(client: TestClient) -> None:
    response = client.post(
        "/api/v1/admin/users/new.person@x.com/grants",
        json={"scope_path": OPS, "name": "New Person"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "New Person"


@pytest.mark.parametrize("path", ["org", "other/thing", "Org/Spreetail/Bad Path"])
def test_scopes_outside_the_org_tree_or_malformed_are_422(client: TestClient, path: str) -> None:
    grant = client.post(f"/api/v1/admin/users/{PRIYA_EMAIL}/grants", json={"scope_path": path})
    register = client.post("/api/v1/admin/scopes", json={"path": path})

    assert grant.status_code == 422
    assert register.status_code == 422


def test_register_and_list_scopes(client: TestClient, registry: FakeRegistry) -> None:
    created = client.post("/api/v1/admin/scopes", json={"path": "org/spreetail/team/eng/"})
    listed = client.get("/api/v1/admin/scopes", params={"prefix": "org/spreetail/team"})

    assert created.status_code == 201
    assert created.json() == {"scopes": ["org/spreetail/team/eng"]}
    assert listed.json() == {"scopes": ["org/spreetail/team/eng"]}


def test_agent_memory_failure_is_503(client: TestClient, registry: FakeRegistry) -> None:
    registry.error = MemoryUnavailableError("down")

    response = client.post("/api/v1/admin/scopes", json={"path": "org/spreetail/team/x"})

    assert response.status_code == 503


def test_non_admins_and_signed_out_are_refused(client: TestClient) -> None:
    sign_in(client, PRIYA_EMAIL, "Priya Shah")
    forbidden = client.get("/api/v1/admin/users")
    client.post("/api/v1/auth/logout")
    signed_out = client.get("/api/v1/admin/users")

    assert forbidden.status_code == 403
    assert signed_out.status_code == 401
