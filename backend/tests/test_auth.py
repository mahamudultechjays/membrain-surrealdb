from typing import Any

import pytest
from authlib.integrations.starlette_client import OAuthError
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.oauth import get_oauth_client
from app.domain.errors import MemoryUnavailableError
from app.main import app
from app.services.access import AccessService
from tests.conftest import FakeRegistry, sign_in


class FakeOAuth:
    def __init__(self, userinfo: dict[str, Any] | None = None, error: Exception | None = None):
        self.userinfo = userinfo or {"email": "Arun.Das@Spreetail.com", "name": "Arun Das"}
        self.error = error

    async def authorize_redirect(self, request: Any, redirect_uri: str) -> RedirectResponse:
        return RedirectResponse(f"https://login.example.com/?redirect_uri={redirect_uri}")

    async def authorize_access_token(self, request: Any) -> dict[str, Any]:
        if self.error:
            raise self.error
        return {"userinfo": self.userinfo}


@pytest.mark.usefixtures("access")
def test_me_needs_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_dev_login_creates_default_scopes_once(
    client: TestClient, access: AccessService, registry: FakeRegistry
) -> None:
    sign_in(client, "Priya.Shah@x.com", "Priya Shah")
    sign_in(client, "priya.shah@x.com", "Priya Shah")

    body = client.get("/api/v1/auth/me").json()

    assert body["email"] == "priya.shah@x.com"
    assert body["is_admin"] is False
    assert body["grants"] == [
        {"scope_path": "org/spreetail", "access": "read", "layer": "org", "owner": None},
        {
            "scope_path": "org/spreetail/user/priya_shah",
            "access": "write",
            "layer": "personal",
            "owner": "Priya Shah",
        },
    ]
    assert registry.ensured == ["org/spreetail/user/priya_shah"]


@pytest.mark.usefixtures("access")
def test_admin_flag_and_logout(client: TestClient) -> None:
    sign_in(client, "admin@x.com", "Ada Admin")

    assert client.get("/api/v1/auth/me").json()["is_admin"] is True
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_dev_login_off_is_404(
    client: TestClient, access: AccessService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEV_LOGIN_ENABLED", False)

    response = client.post("/api/v1/auth/dev-login", json={"email": "a@x.com", "name": "A"})

    assert response.status_code == 404


def test_scope_setup_failure_is_503_and_no_session(
    client: TestClient, access: AccessService, registry: FakeRegistry
) -> None:
    registry.error = MemoryUnavailableError("down")

    response = client.post("/api/v1/auth/dev-login", json={"email": "a@x.com", "name": "A B"})

    assert response.status_code == 503
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.usefixtures("access")
def test_config_reports_available_logins(client: TestClient) -> None:
    assert client.get("/api/v1/auth/config").json() == {
        "sso_enabled": settings.sso_configured,
        "dev_login_enabled": True,
    }


@pytest.mark.usefixtures("access")
def test_sso_not_configured_is_503(client: TestClient) -> None:
    app.dependency_overrides[get_oauth_client] = lambda: None

    assert client.get("/api/v1/auth/login", follow_redirects=False).status_code == 503
    assert client.get("/api/v1/auth/callback").status_code == 503


@pytest.mark.usefixtures("access")
def test_sso_login_redirects_to_entra_with_our_callback(client: TestClient) -> None:
    app.dependency_overrides[get_oauth_client] = lambda: FakeOAuth()

    response = client.get("/api/v1/auth/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith(settings.azure_redirect_uri)


@pytest.mark.usefixtures("access")
def test_sso_callback_signs_in_and_redirects_home(client: TestClient) -> None:
    app.dependency_overrides[get_oauth_client] = lambda: FakeOAuth()

    response = client.get("/api/v1/auth/callback", follow_redirects=False)
    me = client.get("/api/v1/auth/me").json()

    assert response.status_code == 302
    assert response.headers["location"] == settings.FRONTEND_URL
    assert me["email"] == "arun.das@spreetail.com"
    assert me["grants"][1]["scope_path"] == "org/spreetail/user/arun_das"


@pytest.mark.parametrize(
    ("oauth", "code"),
    [
        (FakeOAuth(error=OAuthError("access_denied")), 401),
        (FakeOAuth(userinfo={"name": "No Email"}), 401),
    ],
)
@pytest.mark.usefixtures("access")
def test_sso_callback_failures(client: TestClient, oauth: FakeOAuth, code: int) -> None:
    app.dependency_overrides[get_oauth_client] = lambda: oauth

    assert client.get("/api/v1/auth/callback").status_code == code
