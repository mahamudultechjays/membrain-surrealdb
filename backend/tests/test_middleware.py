import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import TraceMiddleware
from app.services.logger import format_event


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_every_response_gets_a_trace_id(client: TestClient) -> None:
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"].startswith("t-")


def test_request_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="membrain.trace"):
        client.get("/ping")

    [line] = [r.getMessage() for r in caplog.records if r.name == "membrain.trace"]
    assert line.startswith("[HTTP] trace_id=t-")
    assert "method=GET path=/ping status=200" in line


def test_format_event_drops_none_fields() -> None:
    assert (
        format_event("[CAPTURE]", scope="org/user/u-0001", extracted=7, note=None, cost=4200)
        == "[CAPTURE] scope=org/user/u-0001 extracted=7 cost=4200"
    )
