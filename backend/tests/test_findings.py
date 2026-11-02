from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_tests_catalogue(client: TestClient) -> None:
    body = client.get("/api/v1/findings/tests").json()

    assert body["checked"] == "2026-11-02"
    assert len(body["tests"]) == 153
    first = body["tests"][0]
    assert (first["id"], first["requirement"], first["status"]) == ("M1.1", "M1", "pass")
    assert {t["status"] for t in body["tests"]} == {"pass", "fail", "open"}


def test_capabilities_catalogue(client: TestClient) -> None:
    body = client.get("/api/v1/findings/capabilities").json()

    screens = {c["screen"] for c in body["capabilities"] if c["screen"]}
    assert screens == {"capture", "ask", "scoping"}
    assert any(c["area"].startswith("Plan check") for c in body["capabilities"])


def test_gaps_catalogue(client: TestClient) -> None:
    body = client.get("/api/v1/findings/gaps").json()

    assert len(body["gaps"]) == 40
    assert body["gaps"][0]["id"] == "M1"
    assert all(g["name"] and g["agent_memory_today"] for g in body["gaps"])
