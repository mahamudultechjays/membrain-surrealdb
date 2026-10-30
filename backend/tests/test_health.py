import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeProbe


def test_liveness_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_ok_when_agent_memory_answers(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "agent_memory": "ok"}


@pytest.mark.parametrize("memory", ["unavailable", "not_configured"])
def test_readiness_503_otherwise(client: TestClient, probe: FakeProbe, memory: str) -> None:
    probe.status = memory  # type: ignore[assignment]

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "agent_memory": memory}
