from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.composition import get_memory_probe
from app.domain.ports.memory_probe import MemoryStatus
from app.main import app


class FakeProbe:
    def __init__(self, status: MemoryStatus = "ok") -> None:
        self.status: MemoryStatus = status

    async def check(self) -> MemoryStatus:
        return self.status


@pytest.fixture
def probe() -> FakeProbe:
    return FakeProbe()


@pytest.fixture
def client(probe: FakeProbe) -> Iterator[TestClient]:
    app.dependency_overrides[get_memory_probe] = lambda: probe
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
