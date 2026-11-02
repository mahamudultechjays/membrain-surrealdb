import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.middleware import ScopeContextMiddleware
from app.core.config import Settings
from app.services.logger import format_event


@pytest.fixture
def scoped_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(ScopeContextMiddleware, key_scopes={"k-priya": "org/user/u-0001"})

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str | None]:
        return {"scope": request.state.scope}

    return TestClient(app)


def test_valid_key_sets_scope(scoped_client: TestClient) -> None:
    response = scoped_client.get("/whoami", headers={"X-API-Key": "k-priya"})

    assert response.status_code == 200
    assert response.json() == {"scope": "org/user/u-0001"}
    assert response.headers["X-Trace-Id"].startswith("t-")


def test_no_key_passes_through_without_scope(scoped_client: TestClient) -> None:
    response = scoped_client.get("/whoami")

    assert response.status_code == 200
    assert response.json() == {"scope": None}


def test_unknown_key_is_rejected(scoped_client: TestClient) -> None:
    response = scoped_client.get("/whoami", headers={"X-API-Key": "nope"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}
    assert "X-Trace-Id" in response.headers


def test_request_is_logged(scoped_client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="membrain.trace"):
        scoped_client.get("/whoami", headers={"X-API-Key": "k-priya"})

    [line] = [r.getMessage() for r in caplog.records if r.name == "membrain.trace"]
    assert line.startswith("[HTTP] trace_id=t-")
    assert "path=/whoami status=200 scope=org/user/u-0001" in line


def test_format_event_drops_none_fields() -> None:
    assert (
        format_event("[CAPTURE]", scope="org/user/u-0001", extracted=7, note=None, cost=4200)
        == "[CAPTURE] scope=org/user/u-0001 extracted=7 cost=4200"
    )


def test_api_key_scopes_skips_unset_keys() -> None:
    config = Settings(
        _env_file=None,  # type: ignore[call-arg]
        MEMBRAIN_USER_PRIYA_KEY=SecretStr("k-priya"),
        MEMBRAIN_USER_ARUN_KEY=SecretStr(""),
        MEMBRAIN_USER_DEENA_KEY=None,
    )

    assert config.api_key_scopes() == {"k-priya": "org/user/u-0001"}
