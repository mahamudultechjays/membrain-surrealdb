from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_database_probe
from app.main import app


class FakeProbe:
    def __init__(self, healthy: bool) -> None:
        self.healthy = healthy

    async def ping(self) -> bool:
        return self.healthy


@pytest.fixture
def probe() -> FakeProbe:
    return FakeProbe(healthy=True)


@pytest.fixture
def client(probe: FakeProbe) -> Iterator[TestClient]:
    # Not used as a context manager, so the lifespan (and its real SurrealDB
    # connection) never runs; the probe is swapped for a fake instead.
    app.dependency_overrides[get_database_probe] = lambda: probe
    yield TestClient(app)
    app.dependency_overrides.clear()
